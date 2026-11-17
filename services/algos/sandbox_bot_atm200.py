"""Sandbox-mode executor of the frozen ATM 200-point call credit spread, beside the S3n bot.

The entry, the gates and the exit thresholds come only from services/algos/atm200_rule.py and are
not changed here. The order safety comes from services/algos/sandbox_bot.py: this module subclasses
``sb.Bot`` and reuses its ``_place``, ``_settle``, ``_attention``, ``require_sandbox`` and hedge-first
exit, so no order path is copied. The one difference is the strategy label, which the shared order
code takes from a module constant; ``_StrategyClient`` rewrites that label and nothing else.

The caller supplies the client, the time, the holidays and the latest previous VIX close. Nothing in
this module reads a file or the clock, so it runs in tests with a fake client.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from services.algos import atm200_rule as rule
from services.algos import sandbox_bot as sb

STRATEGY = "ATM200-sandbox"
#: A previous VIX close older than this is not used for the gate; the entry goes ahead with the note.
STALE_VIX_DAYS = 5
VIX_STALE_NOTE = "VIX series is stale: gate not applied."
REASON_EXPIRY_WINDOW = (
    "The nearest weekly expiry is not 1 to 6 days away, or no session is left before it."
)
#: States in which something is held or is waiting on a person. A new entry is refused meanwhile.
ACTIVE_ATM = ("entering", "open", "orphan_hedge", "short_bought_back")
#: Fields written before an exit is sent, removed again if that exit is refused or fails.
EXIT_FIELDS = ("exit_reason", "exit_value_quote", "exit_note", "exit_decided")
#: The 15:00 check on the session after entry is the last bar. A check up to 15:05 still counts.
LAST_BAR = time(15, 0)
LAST_BAR_GRACE_END = time(15, 5)
TRADE_COLUMNS = [
    "entry_date",
    "entry_time",
    "expiry",
    "exit_session",
    "sold",
    "long",
    "sold_strike",
    "bought_strike",
    "quantity",
    "vix_prev",
    "note",
    "entry_ltp_credit",
    "credit_points",
    "short_fill_price",
    "hedge_fill_price",
    "buyback_fill_price",
    "sell_hedge_fill_price",
    "exit_time",
    "exit_reason",
    "exit_note",
    "exit_value_points",
    "gross_rupees",
]


class _StrategyClient:
    """Sends the shared order code's requests under this bot's strategy name."""

    def __init__(self, client: Any, strategy: str):
        self.client, self.strategy = client, strategy

    def post(self, path: str, **payload) -> dict:
        if "strategy" in payload:
            payload["strategy"] = self.strategy
        return self.client.post(path, **payload)


def is_trading_day(day: date, holidays: set[date]) -> bool:
    return day.weekday() < 5 and day not in holidays


def next_session(after: date, holidays: set[date]) -> date:
    """The first trading day after ``after``."""
    day = after + timedelta(days=1)
    while not is_trading_day(day, holidays):
        day += timedelta(days=1)
    return day


def expiry_window_ok(today: date, expiry: date, holidays: set[date]) -> bool:
    """The expiry is 1 to 6 calendar days away and at least one session falls before it."""
    days = (expiry - today).days
    return 1 <= days <= rule.MAX_DAYS_TO_EXPIRY and next_session(today, holidays) <= expiry


def vix_gate_input(today: date, latest: tuple[date, float] | None) -> tuple[float | None, str]:
    """The previous VIX close the gate may use, and the note for the state and the alert.

    A missing or stale close is not a skip: the gate is not applied and the note says so.
    """
    if latest is None or (today - latest[0]).days > STALE_VIX_DAYS:
        return None, VIX_STALE_NOTE
    return latest[1], ""


def _ltp(quote: dict) -> float | None:
    value = float(quote.get("ltp") or 0)
    return value if value > 0 else None


def _price(record: dict, key: str) -> float | str:
    fill = record.get(key)
    return fill["price"] if fill else ""


def trade_row(record: dict) -> dict:
    row = {column: record.get(column, "") for column in TRADE_COLUMNS}
    row.update(
        short_fill_price=_price(record, "short_fill"),
        hedge_fill_price=_price(record, "hedge_fill"),
        buyback_fill_price=_price(record, "buyback_fill"),
        sell_hedge_fill_price=_price(record, "sell_hedge_fill"),
    )
    return row


def append_trade(path: Path, record: dict) -> bool:
    """Write one CSV row for a closed trade. A trade already in the file is not written again."""
    key = (record["entry_date"], record["sold"])
    if path.is_file():
        with path.open(newline="", encoding="utf-8") as handle:
            if any((r["entry_date"], r["sold"]) == key for r in csv.DictReader(handle)):
                return False
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.is_file()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRADE_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(trade_row(record))
    return True


class ATM200Bot(sb.Bot):
    def __init__(
        self,
        client: Any,
        state_path: Path,
        trades_path: Path,
        notify=print,
        sleep=lambda seconds: None,
        wait: int = sb.FILL_WAIT_SECONDS,
    ):
        super().__init__(_StrategyClient(client, STRATEGY), state_path, notify, sleep, wait)
        self.trades_path = trades_path

    # entry ----------------------------------------------------------------------------------
    def enter_spread(
        self,
        expiry: date,
        now: datetime,
        holidays: set[date],
        vix_latest: tuple[date, float] | None,
        dry_run: bool = False,
    ) -> dict:
        """Open the spread at about 10:15 on a trading day when the gates pass and nothing is recorded."""
        self.require_sandbox()
        today = now.date()
        if not is_trading_day(today, holidays):
            raise sb.Refused("Today is not a trading day, so no entry was placed.")
        state = self.state()
        if state.get("status") in ACTIVE_ATM:
            raise sb.Refused(
                f"A trade is still recorded ({state['status']}), so nothing new was placed."
            )
        if state.get("entry_date") == today.isoformat():
            raise sb.Refused("An entry was already recorded today, so nothing new was placed.")
        if not expiry_window_ok(today, expiry, holidays):
            return self._skip(today, expiry, REASON_EXPIRY_WINDOW, "", dry_run)

        spot = float(self.quote(sb.UNDERLYING, "NSE_INDEX").get("ltp") or 0)
        if not spot:
            raise sb.Refused("The Nifty quote is missing, so no order was placed.")
        vix_prev, note = vix_gate_input(today, vix_latest)
        sold_strike = rule.atm_strike(spot)
        bought_strike = sold_strike + rule.WIDTH
        sold_sym = sb.contract_symbol(expiry, sold_strike)
        long_sym = sb.contract_symbol(expiry, bought_strike)
        sold_quote, long_quote = self.quote(sold_sym), self.quote(long_sym)
        decision = rule.plan_entry(spot, vix_prev, _ltp(sold_quote), _ltp(long_quote))
        if decision.skipped_reason:
            return self._skip(today, expiry, decision.skipped_reason, note, dry_run)
        sell_at, buy_at = sb.limit_prices(sold_quote, long_quote)

        qty = sb.lot_quantity(now)
        plan = {
            "entry_date": today.isoformat(),
            "entry_time": f"{now:%Y-%m-%d %H:%M}",
            "expiry": expiry.isoformat(),
            "exit_session": next_session(today, holidays).isoformat(),
            "sold": sold_sym,
            "long": long_sym,
            "sold_strike": sold_strike,
            "bought_strike": bought_strike,
            "quantity": qty,
            "entry_ltp_credit": decision.credit_points,
            "vix_prev": vix_prev,
            "note": note,
            "sell_at": sell_at,
            "buy_at": buy_at,
        }
        if dry_run:
            return {"status": "dry_run", **plan}

        # The claim is recorded before the first order, so a crash mid-entry is seen as needing a person.
        self.save({**plan, "status": "entering"})
        try:
            hedge_id = self._place(long_sym, "BUY", qty, "LIMIT", buy_at)
        except sb.Refused:
            # Nothing was accepted, so the claim is released; the day is still used up.
            self.save(self._day(today, "not_placed"))
            raise
        try:
            hedge = self._settle(hedge_id, qty)
        except sb.Unresolved as why:
            self._attention({**plan, "status": "orphan_hedge"}, why)
            raise
        if hedge is None:
            state = {**plan, "status": "no_hedge"}
            self.save(state)
            self.notify(
                f"ATM 200 sandbox bot: the bought call {long_sym} did not fill, so the sold call was not placed. Nothing is open."
            )
            return state

        # The hedge is held from here on: record it before anything else can go wrong.
        state = {**plan, "status": "orphan_hedge", "hedge_fill": hedge.__dict__}
        self.save(state)
        try:
            short_id = self._place(sold_sym, "SELL", qty, "LIMIT", sell_at)
        except sb.Refused as why:
            self._attention(state, why)
            raise
        try:
            short = self._settle(short_id, qty)
        except sb.Unresolved as why:
            self._attention(state, why)
            raise
        if short is None:
            self._attention(state, sb.Unresolved(f"the sold call {sold_sym} did not fill"))
            return state

        credit = short.price - hedge.price
        state = {
            **plan,
            "status": "open",
            "hedge_fill": hedge.__dict__,
            "short_fill": short.__dict__,
            "credit_points": credit,
        }
        self.save(state)
        suffix = f" {note}" if note else ""
        self.notify(
            f"ATM 200 sandbox bot: opened {sold_sym} / {long_sym}, {qty} qty, credit {credit:.2f} "
            f"points (limits {sell_at:.2f} / {buy_at:.2f}), exit session {plan['exit_session']}.{suffix}"
        )
        return state

    def _skip(self, today: date, expiry: date, why: str, note: str, dry_run: bool) -> dict:
        if not dry_run:
            self.save(
                {
                    "entry_date": today.isoformat(),
                    "expiry": expiry.isoformat(),
                    "status": "skipped",
                    "reason": why,
                    "note": note,
                }
            )
        suffix = f" {note}" if note else ""
        self.notify(f"ATM 200 sandbox bot: no entry today. {why}{suffix}")
        return {"status": "skipped", "reason": why, "note": note}

    @staticmethod
    def _day(today: date, status: str) -> dict:
        return {"entry_date": today.isoformat(), "status": status}

    # check and exit -------------------------------------------------------------------------
    def check_spread(self, now: datetime, holidays: set[date], dry_run: bool = False) -> dict:
        """Run every 5 minutes from 10:20 to 15:00. Confirms the legs are held, then applies the rule.

        A check never opens anything. A position that is not reconciled is left alone and alerted,
        because closing a leg against a book that does not match could open a new naked position.
        """
        self.require_sandbox()
        state = self.state()
        status = state.get("status")
        if status == "closed":
            append_trade(self.trades_path, state)  # repairs a close whose CSV row was not written
            return {"status": "closed"}
        if status not in ACTIVE_ATM:
            return {"status": status or "flat"}
        if status == "entering" or status == "orphan_hedge":
            if not state.get("needs_attention"):
                self._attention(
                    state, sb.Unresolved(f"the trade is recorded as {status} and not finished")
                )
            return {"status": "needs_attention", "recorded": status}

        today = now.date()
        if not is_trading_day(today, holidays):
            return {"status": "no_session"}
        reconcile = super().check()
        if reconcile["status"] != "ok":
            return reconcile
        if status == "short_bought_back":
            if dry_run:
                return {"status": "dry_run", "would": "sell the hedge"}
            return self._close(state, now)

        exit_session = date.fromisoformat(state["exit_session"])
        sold_ltp = _ltp(self.quote(state["sold"]))
        long_ltp = _ltp(self.quote(state["long"]))
        if sold_ltp is None or long_ltp is None:
            return {"status": "no_price"}
        value = rule.spread_value(sold_ltp, long_ltp)
        due = today > exit_session or (today == exit_session and now.time() >= LAST_BAR)
        on_time = today == exit_session and LAST_BAR <= now.time() < LAST_BAR_GRACE_END
        reason = rule.exit_decision(state["credit_points"], value, due)
        if reason is None:
            return {"status": "held", "value": value}
        late = due and not on_time
        if dry_run:
            return {"status": "dry_run", "would_exit": reason, "value": value, "late": late}
        decided = {
            **state,
            "exit_reason": reason,
            "exit_value_quote": value,
            "exit_note": "late" if late else "",
            "exit_decided": f"{now:%Y-%m-%d %H:%M}",
        }
        self.save(decided)  # the decision is recorded before the buy-back is sent
        return self._close(decided, now)

    def _release_exit(self) -> None:
        current = self.state()
        if current.get("status") == "open":
            self.save({k: v for k, v in current.items() if k not in EXIT_FIELDS})

    def _close(self, state: dict, now: datetime) -> dict:
        """Buy the call back, then sell the hedge, through the shared exit. Records a closed trade."""
        try:
            done = super().exit(today=None)  # no expiry gate here: the rule decides the exit
        except sb.Unresolved:
            raise
        except sb.Refused:
            self._release_exit()
            raise
        if done.get("status") != "closed":
            if done.get("status") == "exit_failed":
                self._release_exit()
            return done
        exit_value = done["buyback_fill"]["price"] - done["sell_hedge_fill"]["price"]
        record = {
            **done,
            "exit_value_points": exit_value,
            "gross_rupees": rule.pnl_rupees(done["credit_points"], exit_value, done["quantity"]),
            "exit_time": f"{now:%Y-%m-%d %H:%M}",
        }
        self.save(record)
        append_trade(self.trades_path, record)
        late = " (late)" if record.get("exit_note") == "late" else ""
        self.notify(
            f"ATM 200 sandbox bot: closed {record['sold']} / {record['long']} on "
            f"{record['exit_reason']}{late}, gross {record['gross_rupees']:.0f} rupees."
        )
        return record
