"""Live executor of the ATM 200-point call credit spread, built on the Sandbox executor's order path.

This module is a library. It has no entry point, no schedule and no client wiring: a caller builds
``LiveATM200Bot`` with a client, the state and trade paths, the approval path and the injected checks.
Nothing here reads ``.env`` or a real approval file, and nothing here is written by the executor.

It reuses ``services/algos/sandbox_bot_atm200.py`` for the in-flight record, the reconcile, the exit
and the flatten, and ``services/algos/sandbox_bot.py`` for the order code. The differences are set
through the base constructor and two overrides:

- The base's instance attributes are the live label ``ATM200-live``, the alert prefix ``LIVE:`` and
  the venue word ``live``. Every order is sent ``live_only`` and never ``sandbox_only``. The analyzer
  mode must be off, and it is read again before every order.
- Entries alone need the owner's approval for the day, the Live gate (or a written waiver), enough
  cash, no Nifty option position under any label, exactly one lot, the structural cap, and no pilot
  pause. Exits, checks and flattens are never blocked by those: the position is real. The analyzer
  mode still applies to them, because an exit sent in analyzer mode would report success without
  closing anything.
- At most one spread is held. The position check refuses any Nifty option under any label, so a second
  spread cannot be opened while one is held, and no separate position counter is kept.
- The two strikes are chosen once, from one Nifty quote. That quote is used for the margin check and
  passed to the entry, so the margin and the orders always name the same two contracts.
- The structural cap: the spread's largest loss, width x lot x lots, must not exceed the daily cap.

Refusal order for an entry: analyzer mode, clock, time window and trading day, approval, gate, margin,
flat state and positions, quantity, structural cap, pilot pause. The first refusal is the one reported.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from services.algos import atm200_rule as rule
from services.algos import nse_lots
from services.algos import sandbox_bot as sb
from services.algos import sandbox_bot_atm200 as sbx
from utils.logging import get_logger

logger = get_logger(__name__)

# Frozen pilot limits. Changing any of these is a decision for the owner, not an edit in a run.
MAX_LOTS = 1
PAUSE_AT = -10000  # rupees: cumulative pilot net after charges, at or below which entries stop
DAILY_CAP = 27000  # rupees: the largest loss the structural cap allows for one spread
#: Owner decision of 18 Nov 2026: the margin buffer is the larger of the minimum or the share of the margin.
MARGIN_BUFFER_MIN = 3000  # rupees
MARGIN_BUFFER_SHARE = 0.10


def margin_buffer(required: float) -> float:
    """The cash buffer kept above the margin: the larger of Rs 3,000 or 10 percent of the required margin."""
    return max(MARGIN_BUFFER_MIN, MARGIN_BUFFER_SHARE * required)


APPROVAL_EXPIRY = time(15, 30)
ENTRY_FROM = time(10, 15)
ENTRY_UNTIL = time(10, 20)

LIVE_STRATEGY = "ATM200-live"
LIVE_PREFIX = "LIVE:"
LIVE_VENUE = "live"
ORDER_PATH = "/api/v1/placeorder"

MODE_ON = (
    "Analyzer mode is on in OpenAlgo, so the live executor placed nothing. "
    "Switch analyzer mode off, then run the command again."
)
MODE_UNREADABLE = "The analyzer mode could not be read, so the live executor placed nothing."
WINDOW = "Entries are allowed only from 10:15 to 10:20 India time, so nothing was placed."
NOT_TRADING_DAY = "Today is not a trading day, so nothing was placed."
NO_APPROVAL = "No owner approval for today is recorded, so nothing was placed."
APPROVAL_UNREADABLE = "The owner approval file could not be read, so nothing was placed."
APPROVAL_NOT_TODAY = "The owner approval is dated another day, so nothing was placed."
APPROVAL_EXPIRY_BAD = (
    "The owner approval has no valid expiry time for today, so nothing was placed."
)
APPROVAL_EXPIRED = "The owner approval has expired (it ends at 15:30), so no entry was placed."
APPROVAL_STRATEGY = "The owner approval is for another strategy, so nothing was placed."
APPROVAL_LOTS = "The owner approval allows a number of lots other than one, so nothing was placed."
APPROVAL_INCOMPLETE = (
    "The owner approval has no approver or no written time, so nothing was placed."
)
GATE_CLOSED = (
    "The Live gate is on and no written owner waiver covers this rule, so nothing was placed."
)
WAIVER_ALERT = "Live gate bypassed by owner waiver"
MARGIN_SHORT = (
    "Cash of Rs {cash:,.0f} is Rs {short:,.0f} short of the Rs {need:,.0f} needed "
    "(margin Rs {required:,.0f}, bought call premium Rs {premium:,.0f}, "
    "buffer Rs {buffer:,.0f}), so nothing was placed."
)
QUOTE_MISSING = "The Nifty or bought call quote is missing, so nothing was placed."
NOT_FLAT = "A trade is recorded as {status} or an order is unresolved, so nothing new was placed."
POSITION_HELD = (
    "{symbol} already has a position of {qty} in the account under some label, so nothing new "
    "was placed. Look at the positions first."
)
POSITIONS_UNREADABLE = "The positions could not be read, so nothing was placed."
QUANTITY = (
    "The quantity is not exactly one Nifty lot for the {expiry} expiry, so nothing was placed."
)
CAP_REFUSED = (
    "The spread's largest possible loss, {width} x {lot} x {lots} = Rs {loss:,.0f}, is above the "
    "Rs {cap:,.0f} daily cap, so nothing was placed."
)
PAUSED = (
    "The pilot is paused: its cumulative net result is Rs {net:,.0f}, at or below Rs {limit:,.0f}. "
    "Entries stay stopped until the owner clears the pause in the approval file."
)


def _moment(value: Any) -> datetime | None:
    """A naive ISO date-time from the approval file, or None when it cannot be read."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return None if parsed.tzinfo is not None else parsed


def _is_nifty_option(symbol: str) -> bool:
    return symbol.startswith(sb.UNDERLYING) and symbol.endswith(("CE", "PE"))


def _strike_symbols(expiry: date, spot: float) -> tuple[str, str]:
    """(sold call, bought call) for one Nifty price, by the same rule the base entry uses."""
    sold_strike = rule.atm_strike(spot)
    return (
        sb.contract_symbol(expiry, sold_strike),
        sb.contract_symbol(expiry, sold_strike + rule.WIDTH),
    )


class _LiveClient:
    """Guards the injected client for the live path: an order must be built as a live order.

    The shared order code sends ``sandbox_only=True`` on every order. Here that marker is replaced by
    ``live_only=True``, and an order that arrives without the Sandbox marker is refused, never sent.
    Every other request passes through untouched; the label is set by the base's client wrapper.
    """

    def __init__(self, client: Any):
        self.client = client

    def post(self, path: str, **payload) -> dict:
        if path == ORDER_PATH:
            if payload.pop("sandbox_only", None) is not True:
                raise sb.Refused("The order was not built as a live order, so nothing was sent.")
            payload["live_only"] = True
        return self.client.post(path, **payload)


class LiveATM200Bot(sbx.ATM200Bot):
    """The ATM 200 spread executed in Live mode, with the owner's approval and the pilot limits."""

    def __init__(
        self,
        client: Any,
        state_path: Path,
        trades_path: Path,
        approval_path: Path,
        *,
        margin_required: Callable[[str, str, int], float],
        funds_available: Callable[[], float],
        positions: Callable[[], list[dict]],
        live_gate_on: bool,
        notify: Callable[[str], Any] = print,
        sleep: Callable[[float], None] = lambda seconds: None,
        wait: int = sb.FILL_WAIT_SECONDS,
    ):
        super().__init__(
            _LiveClient(client),
            state_path,
            trades_path,
            notify=notify,
            sleep=sleep,
            wait=wait,
            strategy=LIVE_STRATEGY,
            alert_prefix=LIVE_PREFIX,
            venue=LIVE_VENUE,
        )
        self.approval_path = Path(approval_path)
        self._margin_required = (
            margin_required  # span plus exposure, premium excluded: see _margin_or_refuse
        )
        self._funds_available = funds_available
        self._positions = positions
        self._live_gate_on = live_gate_on

    # mode -----------------------------------------------------------------------------------
    def require_live(self) -> None:
        """Refuses unless analyzer mode is confirmed OFF. A reply that cannot be read also refuses."""
        reply = self.client.post("/api/v1/analyzer")
        data = reply.get("data") or {}
        if reply.get("status") != "success" or "analyze_mode" not in data:
            raise sb.Refused(MODE_UNREADABLE)
        if data["analyze_mode"] is True:
            raise sb.Refused(MODE_ON)
        if data["analyze_mode"] is not False:
            raise sb.Refused(MODE_UNREADABLE)

    def require_sandbox(self) -> None:
        """The base class's mode guard, by its name in the shared code. Here it is the Live guard."""
        self.require_live()

    def _mode_or_refuse(self) -> None:
        try:
            self.require_live()
        except sb.Refused as why:
            self._refuse(str(why))

    def _refuse(self, why: str) -> None:
        self.notify(why)
        raise sb.Refused(why)

    # positions ------------------------------------------------------------------------------
    def _refuse_if_held(self, sold_sym: str, long_sym: str) -> None:
        self._refuse_if_nifty_option_held()

    def _refuse_if_nifty_option_held(self) -> None:
        """Refuses while the account holds any Nifty option under any strategy label.

        This is also what keeps the pilot to one spread: a second spread's legs are Nifty options, so
        they are refused here whatever their strikes.
        """
        try:
            rows = list(self._positions())
        except Exception:
            logger.exception("Could not read the positions for the live executor")
            self._refuse(POSITIONS_UNREADABLE)
        for row in rows:
            symbol = str(row.get("symbol") or "")
            qty = int(float(row.get("quantity") or 0))
            if _is_nifty_option(symbol) and qty:
                self._refuse(POSITION_HELD.format(symbol=symbol, qty=qty))

    # the guarded entry ----------------------------------------------------------------------
    def enter_spread(
        self,
        expiry: date,
        now: datetime,
        holidays: set[date],
        vix_latest: tuple[date, float] | None,
        dry_run: bool = False,
    ) -> dict:
        """Opens the live spread once every entry check passes. Exits and flattens do not go through here."""
        self._mode_or_refuse()  # 1
        self._window_or_refuse(now, holidays)  # 2
        approval = self._approval_or_refuse(now)  # 3
        waived = self._gate_or_refuse(approval)  # 4
        spot = self._spot_or_refuse()  # 5: the one Nifty quote; the strikes come from it
        sold_sym, long_sym = _strike_symbols(expiry, spot)
        qty = sb.lot_quantity(now)
        self._margin_or_refuse(sold_sym, long_sym, qty)  # 5
        self._flat_or_refuse()  # 6
        self._refuse_if_nifty_option_held()  # 6
        lot = nse_lots.nifty_lot(expiry)  # 7
        if lot is None or qty != lot * MAX_LOTS:
            self._refuse(QUANTITY.format(expiry=f"{expiry:%d %b %Y}"))
        self._cap_or_refuse(lot)  # 7
        net = sbx.ledger_total(self.trades_path)  # 8
        if net <= PAUSE_AT and approval.get("pause_cleared_on") != now.date().isoformat():
            if not dry_run:
                self.save(
                    {
                        **self.state(),
                        "status": "paused",
                        "paused_on": now.date().isoformat(),
                        "paused_net": round(net, 2),
                    }
                )
            self._refuse(PAUSED.format(net=net, limit=PAUSE_AT))
        if waived:
            self.notify(WAIVER_ALERT)
        return super().enter_spread(expiry, now, holidays, vix_latest, dry_run=dry_run, spot=spot)

    def _window_or_refuse(self, now: datetime, holidays: set[date]) -> None:
        try:
            sbx.assert_india_clock()
        except sb.Refused as why:
            self._refuse(str(why))
        if not sbx.is_trading_day(now.date(), holidays):
            self._refuse(NOT_TRADING_DAY)
        if not ENTRY_FROM <= now.time() < ENTRY_UNTIL:
            self._refuse(WINDOW)

    def _approval_or_refuse(self, now: datetime) -> dict:
        """The owner's approval for today, read from the file the owner writes. Never written here."""
        today = now.date()
        try:
            raw = json.loads(self.approval_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._refuse(NO_APPROVAL)
        except (OSError, ValueError):
            self._refuse(APPROVAL_UNREADABLE)
        if not isinstance(raw, dict):
            self._refuse(APPROVAL_UNREADABLE)
        if raw.get("date") != today.isoformat():
            self._refuse(APPROVAL_NOT_TODAY)
        expires = _moment(raw.get("expires_at"))
        if expires is None or expires.date() != today:
            self._refuse(APPROVAL_EXPIRY_BAD)
        if now >= min(expires, datetime.combine(today, APPROVAL_EXPIRY)):
            self._refuse(APPROVAL_EXPIRED)
        if raw.get("strategy") != LIVE_STRATEGY:
            self._refuse(APPROVAL_STRATEGY)
        if type(raw.get("max_lots")) is not int or raw["max_lots"] != MAX_LOTS:
            self._refuse(APPROVAL_LOTS)
        approver, written = raw.get("approved_by"), raw.get("written_at")
        if not (
            isinstance(approver, str)
            and approver.strip()
            and isinstance(written, str)
            and written.strip()
        ):
            self._refuse(APPROVAL_INCOMPLETE)
        return raw

    def _gate_or_refuse(self, approval: dict) -> bool:
        """True when the Live gate is on and the owner's written waiver lets this entry through."""
        if not self._live_gate_on:
            return False
        waiver = approval.get("gate_waiver")
        if not isinstance(waiver, dict):
            waiver = {}
        sentence = str(waiver.get("owner_sentence") or "").strip()
        if waiver.get("waived") is not True or not sentence:
            self._refuse(GATE_CLOSED)
        return True

    def _spot_or_refuse(self) -> float:
        """The one Nifty quote of the entry. Refuses when it is missing."""
        spot = float(self.quote(sb.UNDERLYING, "NSE_INDEX").get("ltp") or 0)
        if not spot:
            self._refuse(QUOTE_MISSING)
        return spot

    def _margin_or_refuse(self, sold_sym: str, long_sym: str, qty: int) -> None:
        """Cash must cover the required margin, the bought call's premium at its last price, and the buffer.

        ``margin_required(sold_symbol, long_symbol, quantity)`` must return the span plus the exposure
        only, with the premium excluded. The broker's ``total_margin_required`` already includes the
        bought call's premium (measured 18 Nov 2026 on 25300/25500 at one lot: total Rs 49,898 =
        span 12,807 + exposure 32,964 + premium 4,127). The executor adds the premium itself, so a
        runner wiring the app's total must subtract the premium, or the premium is counted twice.
        """
        premium_each = float(self.quote(long_sym).get("ltp") or 0)
        if not premium_each:
            self._refuse(QUOTE_MISSING)
        required = float(self._margin_required(sold_sym, long_sym, qty))
        premium = premium_each * qty
        buffer = margin_buffer(required)
        need = required + premium + buffer
        cash = float(self._funds_available())
        if cash < need:
            self._refuse(
                MARGIN_SHORT.format(
                    cash=cash,
                    short=need - cash,
                    need=need,
                    required=required,
                    premium=premium,
                    buffer=buffer,
                )
            )

    def _cap_or_refuse(self, lot: int) -> None:
        """Refuses when the spread's largest possible loss, width x lot x lots, is above the daily cap."""
        loss = rule.WIDTH * lot * MAX_LOTS
        if loss > DAILY_CAP:
            self._refuse(
                CAP_REFUSED.format(
                    width=rule.WIDTH, lot=lot, lots=MAX_LOTS, loss=loss, cap=DAILY_CAP
                )
            )

    def _flat_or_refuse(self) -> None:
        state = self.state()
        if (
            state.get("inflight")
            or state.get("needs_attention")
            or state.get("status") in sbx.ACTIVE_ATM
        ):
            self._refuse(NOT_FLAT.format(status=state.get("status") or "unresolved"))

    # exits and flattens: the mode is checked, nothing else is -----------------------------------
    def check_spread(self, now: datetime, holidays: set[date], dry_run: bool = False) -> dict:
        self._mode_or_refuse()
        return super().check_spread(now, holidays, dry_run=dry_run)

    def flatten(self, yes: bool = False) -> dict:
        self._mode_or_refuse()
        return super().flatten(yes=yes)
