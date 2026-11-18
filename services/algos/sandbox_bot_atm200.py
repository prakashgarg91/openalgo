"""Sandbox-mode executor of the frozen ATM 200-point call credit spread, beside the S3n bot.

The entry, the gates and the exit thresholds come only from services/algos/atm200_rule.py and are
not changed here. The order safety comes from services/algos/sandbox_bot.py: this module subclasses
``sb.Bot`` and reuses its ``_place``, ``_settle``, ``_attention``, ``require_sandbox`` and hedge-first
exit, so no order path is copied. The strategy label, the alert prefix and the venue word are instance
attributes set by the constructor, so a subclass for another venue (services/algos/live_executor_atm200.py)
changes those three and nothing else. ``_StrategyClient`` rewrites the label in every request and nothing else.

Every order is written to the state as an ``inflight`` record before it is sent, and gets its id
when the reply arrives. If the reply is lost, the next run settles the record against the order book
(cancel what is still working, confirm by position) before it decides anything.

The caller supplies the client, the time, the holidays and the latest previous VIX close. Nothing in
this module reads a file. The one clock read is the machine's UTC offset, checked against India time
before every entry, check and flatten; a test replaces it with ``machine_utc_offset``.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytz

from services.algos import atm200_rule as rule
from services.algos import sandbox_bot as sb
from services.algos.sandbox_round_trips import fill_charges
from utils.logging import get_logger

logger = get_logger(__name__)
STRATEGY = "ATM200-sandbox"
#: Every message a trader reads starts with this label, so a Sandbox alert is never mistaken for Live.
#: The default; an instance sets its own through ``alert_prefix``.
PREFIX = "Sandbox:"
#: The venue as it reads inside a message ("the sandbox account"). An instance sets its own through ``venue``.
VENUE = "sandbox"
#: The base bot's wording, given the prefix. Its "closed" line is dropped: the full exit alert replaces it.
BASE_LABELS = (
    ("Sandbox bot ALERT:", "ATM 200 ALERT:"),
    ("Sandbox bot:", "ATM 200:"),
)
BASE_SUPPRESSED = ("Sandbox bot: closed",)
INDIA_OFFSET = timedelta(hours=5, minutes=30)
CLOCK_MESSAGE = (
    "The computer's clock is not on India time (UTC+05:30), so the bot placed nothing. "
    "Set the Windows time zone to India Standard Time, then run the command again."
)
#: A previous VIX close older than this is not used for the gate; the entry goes ahead with the note.
STALE_VIX_DAYS = 4
VIX_STALE_NOTE = "VIX series is stale: gate not applied."
REASON_EXPIRY_WINDOW = (
    "The nearest weekly expiry is not 1 to 6 days away, or no session is left before it."
)
#: States in which something is held or is waiting on a person. A new entry is refused meanwhile.
ACTIVE_ATM = ("entering", "open", "orphan_hedge", "short_bought_back")
#: Fields written before an exit is sent, removed again if that exit is refused or fails.
EXIT_FIELDS = ("exit_reason", "exit_value_quote", "exit_note", "exit_decided")
#: Entry is refused once the closed trades in the CSV have lost this much, net of charges (the frozen stop).
LEDGER_STOP_TEXT = (
    "The ATM 200 {venue} ledger has lost 20,000 rupees or more, so it has stopped. "
    "A person must decide whether to continue."
)
LEDGER_STOP_MESSAGE = LEDGER_STOP_TEXT.format(venue=VENUE)
#: States a flatten by a person acts on. Anything else is already flat or was never opened.
FLATTEN_STATES = ("entering", "orphan_hedge", "short_bought_back", "open")
FLATTENED = "flattened_by_person"
FLATTEN_NOTE = "Closed by a person with the flatten command. Not written to trades.csv, so its result is not booked."
#: The 15:00 check on the session after entry is the last bar. A check up to 15:05 still counts.
LAST_BAR = time(15, 0)
LAST_BAR_GRACE_END = time(15, 5)
IST = pytz.timezone("Asia/Kolkata")
#: The order book stamps orders with the IST wall clock; sent_at is kept on the same clock.
TERMINAL_ORDER_STATES = ("complete", "rejected", "cancelled")
ENTRY_PURPOSES = ("entry_hedge", "entry_short")
EXIT_PURPOSES = ("buyback", "sell_hedge")
PURPOSE_NAMES = {
    "entry_hedge": "bought call (entry)",
    "entry_short": "sold call (entry)",
    "buyback": "buy-back of the sold call",
    "sell_hedge": "sale of the bought call",
    "flatten_buyback": "flatten buy-back of the sold call",
    "flatten_sell_hedge": "flatten sale of the bought call",
}
#: (trade row column, side of the fill, leg it belongs to) for the four fills a closed trade holds.
FILL_SIDES = (
    ("short_fill_price", "SELL", "entry"),
    ("hedge_fill_price", "BUY", "entry"),
    ("buyback_fill_price", "BUY", "exit"),
    ("sell_hedge_fill_price", "SELL", "exit"),
)
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


class ReplyLost(Exception):
    """OpenAlgo did not answer, so an order may or may not have reached it. Never treated as refused."""


class _StrategyClient:
    """Sends the shared order code's requests under this bot's strategy name."""

    def __init__(self, client: Any, strategy: str):
        self.client, self.strategy = client, strategy

    def post(self, path: str, **payload) -> dict:
        if "strategy" in payload:
            payload["strategy"] = self.strategy
        return self.client.post(path, **payload)

    def post_as_is(self, path: str, **payload) -> dict:
        """Sends a request with its strategy field untouched. Used only for reading another label's holdings."""
        return self.client.post(path, **payload)


def now_ist() -> datetime:
    """The naive IST wall clock, the clock the order book stamps orders with."""
    return datetime.now(IST).replace(tzinfo=None)


def machine_utc_offset() -> timedelta:
    """This computer's UTC offset now. The only clock read in this module; tests replace it."""
    return datetime.now().astimezone().utcoffset()


def assert_india_clock() -> None:
    """Refuses unless this computer is on India time, because order matching assumes that clock.

    A wrong clock would mis-match an order to the wrong record, so nothing is sent in that case.
    """
    if machine_utc_offset() != INDIA_OFFSET:
        raise sb.Refused(CLOCK_MESSAGE)


def labelled(text: str, prefix: str = PREFIX) -> str | None:
    """The text with the alert prefix; None for a base message that the full exit alert replaces."""
    if text.startswith(BASE_SUPPRESSED):
        return None
    for old, new in BASE_LABELS:
        if text.startswith(old):
            return f"{prefix} {new}{text[len(old) :]}"
    return text if text.startswith(prefix) else f"{prefix} ATM 200 {text}"


def safe_send(notify: Callable[[str], Any], text: str, prefix: str = PREFIX) -> None:
    """Sends one alert. A failure is logged and never raised, so an alert can not stop an order path."""
    label = labelled(str(text), prefix)
    if label is None:
        return
    try:
        notify(label)
    except Exception:
        logger.exception("Could not send a sandbox alert; the order step carries on")


def _day(text: str) -> str:
    return date.fromisoformat(text).strftime("%d %b %Y")


def entry_message(record: dict, sell_at: float, buy_at: float, prefix: str = PREFIX) -> str:
    """The entry alert: strikes, expiry, quantity, both credits, the VIX value and date, the exit session."""
    if record.get("vix_prev") is None:
        vix = VIX_STALE_NOTE
    else:
        vix = f"India VIX {record['vix_prev']:.2f} on {_day(record['vix_prev_date'])}."
    return (
        f"{prefix} ATM 200 opened. Sold {record['sold']}, bought {record['long']}, "
        f"expiry {_day(record['expiry'])}, quantity {record['quantity']}. "
        f"LTP credit {record['entry_ltp_credit']:.2f} points, fill credit {record['credit_points']:.2f} "
        f"points (limits {sell_at:.2f} sell, {buy_at:.2f} buy). {vix} "
        f"Exit session {_day(record['exit_session'])}."
    )


EXIT_NAMES = {"target": "the target", "stop": "the stop", "time": "the time exit"}


def _book_time(text: Any) -> datetime:
    """An order book timestamp. One that cannot be read counts as after any send, so it is never skipped."""
    try:
        return datetime.strptime(str(text), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.max


def _expected_held(purpose: str, quantity: int, filled: int) -> tuple[int, int]:
    """(sold call, bought call) the sandbox must hold once this order has filled ``filled`` of ``quantity``."""
    if purpose == "entry_hedge":
        return 0, filled
    if purpose == "entry_short":
        return -filled, quantity
    if purpose == "buyback":
        return -(quantity - filled), quantity
    return 0, quantity - filled  # sell_hedge


def row_charges(row: dict) -> float:
    """Rupees of charges for the fills a closed trade row holds, from the shared charge schedule."""
    quantity = float(row.get("quantity") or 0)
    entry_day = str(row.get("entry_date") or "")
    exit_day = str(row.get("exit_time") or row.get("exit_session") or "")[:10]
    total = 0.0
    for column, action, leg in FILL_SIDES:
        price = row.get(column)
        if price in (None, ""):
            continue
        day = entry_day if leg == "entry" else exit_day
        total += fill_charges(action, quantity, float(price), day)
    return total


def ledger_total(path: Path) -> float:
    """Sum of NET rupees over the closed trades: each row's gross less the charges of its four fills.

    A missing file is an empty ledger. A row without a gross figure counts as 0 for the gross.
    """
    if not path.is_file():
        return 0.0
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(
            float(row.get("gross_rupees") or 0) - row_charges(row) for row in csv.DictReader(handle)
        )


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
        *,
        strategy: str = STRATEGY,
        alert_prefix: str = PREFIX,
        venue: str = VENUE,
    ):
        # Set before the base constructor: the client wrapper and the alerts read them from here on.
        self.strategy, self.alert_prefix, self.venue = strategy, alert_prefix, venue
        super().__init__(
            _StrategyClient(client, strategy),
            state_path,
            lambda text: safe_send(notify, text, self.alert_prefix),
            sleep,
            wait,
        )
        self.trades_path = trades_path
        self._context: str | None = None  # "flatten" while a flatten by a person is running

    # state ----------------------------------------------------------------------------------
    def save(self, state: dict) -> None:
        """Writes the state. A write that says nothing about ``inflight`` keeps the record on disk."""
        if "inflight" not in state:
            state = {**state, "inflight": self.state().get("inflight")}
        super().save(state)

    def _clear_inflight(self) -> None:
        self.save({**self.state(), "inflight": None})

    # orders ---------------------------------------------------------------------------------
    def _purpose(self, state: dict, symbol: str, action: str) -> str:
        if self._context == "flatten":
            return "flatten_buyback" if action == "BUY" else "flatten_sell_hedge"
        if action == "BUY":
            return "buyback" if symbol == state.get("sold") else "entry_hedge"
        return "entry_short" if symbol == state.get("sold") else "sell_hedge"

    def _place(
        self, symbol: str, action: str, quantity: int, pricetype: str, price: float = 0.0
    ) -> str:
        """Sends one order through the shared code, recording it as inflight before it leaves.

        A refusal from OpenAlgo is an answer that nothing was accepted, so the record is cleared.
        Any other failure (timeout, lost reply, interrupt) keeps the record for the reconcile.
        """
        state = self.state()
        if state.get("inflight"):
            raise sb.Unresolved(
                "An earlier order is still unresolved, so nothing new was placed. It is settled first."
            )
        record = {
            "side": action,
            "symbol": symbol,
            "quantity": quantity,
            "sent_at": now_ist().isoformat(timespec="seconds"),
            "purpose": self._purpose(state, symbol, action),
        }
        self.save({**state, "inflight": record})
        try:
            orderid = super()._place(symbol, action, quantity, pricetype, price)
        except sb.Refused:
            self._clear_inflight()
            raise
        self.save({**self.state(), "inflight": {**record, "orderid": orderid}})
        return orderid

    def _settle(self, orderid: str, quantity: int) -> sb.Fill | None:
        """Waits for the fill as the shared code does. Once the order is finished, its record is cleared.

        An unresolved order (raised) keeps the record, so the next run settles it.
        """
        fill = super()._settle(orderid, quantity)
        self._clear_inflight()
        return fill

    def _order_book(self) -> list[dict]:
        reply = self.client.post("/api/v1/orderbook")
        if reply.get("status") != "success":
            raise ReplyLost("the order book did not answer with a success")
        return list((reply.get("data") or {}).get("orders") or [])

    def _order_status(self, orderid: str) -> dict:
        reply = self.client.post("/api/v1/orderstatus", strategy=self.strategy, orderid=orderid)
        return reply.get("data") or {}

    # reconcile ------------------------------------------------------------------------------
    def _match(self, inflight: dict, book: list[dict]) -> list[dict]:
        """The book rows that are this record's order: by id once the reply gave one, otherwise by
        symbol, side, this strategy, and a time at or after the send."""
        if inflight.get("orderid"):
            return [o for o in book if str(o.get("orderid")) == str(inflight["orderid"])]
        sent = datetime.fromisoformat(inflight["sent_at"])
        return [
            o
            for o in book
            if o.get("symbol") == inflight["symbol"]
            and o.get("action") == inflight["side"]
            and o.get("strategy") == self.strategy
            and _book_time(o.get("timestamp")) >= sent
        ]

    def _hold(self, state: dict, why: str) -> dict:
        """Keeps the state as it is, flags it for a person, and alerts once for the same reason."""
        if state.get("needs_attention") != why:
            self.notify(
                f"{self.alert_prefix} ATM 200 ALERT: {why} Look at the positions and the order book now."
            )
        self.save({**state, "needs_attention": why})
        return {"status": "needs_attention", "reason": why}

    def _outcome(
        self, purpose: str, state: dict, fill: sb.Fill, quantity: int
    ) -> tuple[dict, str | None]:
        """The state a resolved order leaves, and the problem a person must look at (None when clean)."""
        filled = fill.quantity
        if purpose == "entry_hedge":
            if filled == 0:
                return {**state, "status": "no_hedge"}, None
            if filled < quantity:
                return {**state, "status": "orphan_hedge"}, (
                    f"Only {filled} of {quantity} of the bought call filled."
                )
            return {**state, "status": "orphan_hedge", "hedge_fill": fill.__dict__}, None
        if purpose == "entry_short":
            if filled == 0:
                # Only the bought call is held. The check flags it; flatten closes it.
                return state, None
            if filled < quantity:
                return state, f"Only {filled} of {quantity} of the sold call filled."
            hedge = state.get("hedge_fill")
            if not hedge:
                return state, "The bought call's fill is not recorded, so the credit is unknown."
            credit = fill.price - hedge["price"]
            return {
                **state,
                "status": "open",
                "short_fill": fill.__dict__,
                "credit_points": credit,
            }, None
        if purpose == "buyback":
            if filled == quantity:
                return {**state, "buyback_fill": fill.__dict__, "status": "short_bought_back"}, None
            if filled == 0:
                return (
                    state,
                    "The buy-back did not fill after the cancel, so the sold call is still held.",
                )
            return state, f"Only {filled} of {quantity} of the sold call was bought back."
        if purpose == "sell_hedge":
            if filled == quantity:
                return {**state, "sell_hedge_fill": fill.__dict__, "status": "closed"}, None
            if filled == 0:
                return state, "The sale of the bought call did not fill after the cancel."
            return state, f"Only {filled} of {quantity} of the bought call was sold."
        key = "flatten_buyback_fill" if purpose == "flatten_buyback" else "flatten_sell_hedge_fill"
        if filled == quantity:
            return {**state, key: fill.__dict__}, None
        if filled == 0:
            return state, None
        return state, f"Only {filled} of {quantity} filled for the {PURPOSE_NAMES[purpose]}."

    def _reconcile(self, now: datetime, stop: bool) -> dict | None:
        """Settles an order whose reply was lost, before any new decision is made.

        Finds the order in the order book, cancels it if it is still working, confirms the result
        against the account's positions, and records the outcome and the held quantities. Returns
        None when there is nothing to settle, or when a clean result may be used by the caller
        (``stop=False``). Otherwise returns a result for the caller to return. With ``stop=True``
        (checks and entries) every resolution returns, so the next run acts on the recovered state.
        """
        state = self.state()
        inflight = state.get("inflight")
        if not inflight:
            return None
        purpose, quantity = inflight["purpose"], int(inflight["quantity"])
        name = PURPOSE_NAMES[purpose]
        try:
            matches = self._match(inflight, self._order_book())
            if len(matches) > 1:
                return self._hold(
                    state, f"More than one order matches the {name} sent at {inflight['sent_at']}."
                )
            if not matches:
                # The order never reached OpenAlgo: nothing is held for it and nothing was placed.
                cleared = {**state, "inflight": None}
                if purpose == "entry_hedge":
                    cleared["status"] = "not_placed"
                return self._hold(
                    cleared,
                    f"The {name} order never reached OpenAlgo, so nothing was placed for it.",
                )
            order = matches[0]
            orderid = str(order["orderid"])
            if str(order.get("order_status", "")).lower() not in TERMINAL_ORDER_STATES:
                self._cancel(orderid)
                order = self._order_status(orderid)
                if str(order.get("order_status", "")).lower() not in TERMINAL_ORDER_STATES:
                    return self._hold(
                        state, f"Order {orderid} for the {name} is still working after a cancel."
                    )
            status = str(order.get("order_status", "")).lower()
            fill = sb.Fill(
                orderid,
                float(order.get("average_price") or 0),
                int(float(order.get("filled_quantity") or 0)),
            )
            held_sold = self._held(state["sold"], self.strategy)
            held_long = self._held(state["long"], self.strategy)
            if purpose in ENTRY_PURPOSES or purpose in EXIT_PURPOSES:
                want = _expected_held(purpose, quantity, fill.quantity)
                if (held_sold, held_long) != want:
                    return self._hold(
                        state,
                        f"After order {orderid} ({name}) the {self.venue} holds the sold call at {held_sold} "
                        f"and the bought call at {held_long}, not the {want[0]} and {want[1]} expected.",
                    )
            new, problem = self._outcome(purpose, state, fill, quantity)
            new = {k: v for k, v in new.items() if k != "needs_attention"}
            summary = (
                f"Reconciled the {name} (order {orderid}): {status}, {fill.quantity} of {quantity} "
                f"filled at {fill.price:.2f}. Held: sold call {held_sold}, bought call {held_long}."
            )
            new["inflight"] = None
            new["reconcile_note"] = f"{summary} At {now:%Y-%m-%d %H:%M}."
            if problem:
                return self._hold(new, problem)
            if purpose == "sell_hedge" and new.get("status") == "closed":
                self._book(new, now)
            else:
                self.save(new)
            self.notify(f"{self.alert_prefix} ATM 200 ALERT: {summary} Check the positions now.")
            if not stop:
                return None
            return {
                "status": "mismatch" if purpose in EXIT_PURPOSES else "needs_attention",
                "reconciled": purpose,
                "orderid": orderid,
            }
        except Exception:
            return self._hold(
                state,
                f"Could not settle the {name} order because the order book or the cancel did not answer. "
                "The record is kept, and nothing new is placed until it is settled.",
            )

    # entry ----------------------------------------------------------------------------------
    def enter_spread(
        self,
        expiry: date,
        now: datetime,
        holidays: set[date],
        vix_latest: tuple[date, float] | None,
        dry_run: bool = False,
        spot: float | None = None,
    ) -> dict:
        """Open the spread at about 10:15 on a trading day when the gates pass and nothing is recorded.

        ``spot`` is the Nifty price the caller already quoted and used to choose the strikes. None quotes
        it here. A given spot is used as it is: the strikes are not taken again from a second quote.
        """
        assert_india_clock()
        self.require_sandbox()
        if self.state().get("inflight"):
            if dry_run:
                return {"status": "dry_run", "would": "settle the unresolved order first"}
            pending = self._reconcile(now, stop=True)
            if pending is not None:
                return pending
        if rule.ledger_should_stop(ledger_total(self.trades_path)):
            ledger_stop = LEDGER_STOP_TEXT.format(venue=self.venue)
            self.notify(f"{self.alert_prefix} ATM 200: {ledger_stop}")
            raise sb.Refused(ledger_stop)
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

        if spot is None:
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
        self._refuse_if_held(sold_sym, long_sym)
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
            "vix_prev_date": vix_latest[0].isoformat() if vix_prev is not None else "",
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
                f"{self.alert_prefix} ATM 200: the bought call {long_sym} did not fill, so the sold call was not placed. Nothing is open."
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
        self.notify(entry_message(state, sell_at, buy_at, self.alert_prefix))
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
        self.notify(f"{self.alert_prefix} ATM 200: no entry today. {why}{suffix}")
        return {"status": "skipped", "reason": why, "note": note}

    @staticmethod
    def _day(today: date, status: str) -> dict:
        return {"entry_date": today.isoformat(), "status": status}

    def _held(self, symbol: str, label: str) -> int:
        """Net quantity the account holds in the contract under one strategy label (negative = short)."""
        reply = self.client.post_as_is(
            "/api/v1/openposition",
            strategy=label,
            symbol=symbol,
            exchange=sb.EXCHANGE,
            product=sb.PRODUCT,
        )
        return int(float(reply.get("quantity") or 0))

    def _refuse_if_held(self, sold_sym: str, long_sym: str) -> None:
        """Refuse an entry when either contract already has a position under any strategy label.

        Two bots must not both hold the same contract: the other bot's position would be mistaken for
        this bot's, and a flatten by either would close the other's leg. The account's positionbook
        covers every label; the two labels named here are also asked, as the earlier check did.
        """
        reply = self.client.post_as_is("/api/v1/positionbook")
        if reply.get("status") != "success":
            why = "The positions could not be read, so no order was placed."
            self.notify(f"{self.alert_prefix} ATM 200: {why}")
            raise sb.Refused(why)
        for position in reply.get("data") or []:
            symbol = position.get("symbol")
            if symbol in (sold_sym, long_sym) and int(float(position.get("quantity") or 0)):
                why = (
                    f"{symbol} already has a position of {position.get('quantity')} in the {self.venue} "
                    "account, so nothing new was placed. Look at the positions first."
                )
                self.notify(f"{self.alert_prefix} ATM 200: {why}")
                raise sb.Refused(why)
        for symbol in (sold_sym, long_sym):
            for label in (sb.STRATEGY, self.strategy):
                qty = self._held(symbol, label)
                if qty:
                    why = (
                        f"{symbol} already has a position of {qty} in the {self.venue} account, so "
                        "nothing new was placed. Look at the positions first."
                    )
                    self.notify(f"{self.alert_prefix} ATM 200: {why}")
                    raise sb.Refused(why)

    # check and exit -------------------------------------------------------------------------
    def check_spread(self, now: datetime, holidays: set[date], dry_run: bool = False) -> dict:
        """Run every 5 minutes from 10:20 to 15:00. Settles any lost order, confirms the legs are held, then applies the rule.

        A check never opens anything. A position that is not reconciled is left alone and alerted,
        because closing a leg against a book that does not match could open a new naked position.
        """
        assert_india_clock()
        self.require_sandbox()
        if self.state().get("inflight"):
            if dry_run:
                return {"status": "dry_run", "would": "settle the unresolved order first"}
            pending = self._reconcile(now, stop=True)
            if pending is not None:
                return pending
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
        if state.get("needs_attention"):
            # Set by a reconcile that could not finish. Nothing is sent until a person clears it.
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
        # Thresholds use the LTP credit at entry, the same basis as the replay and as the LTP value they are
        # compared with. Profit and loss is still booked on the fills: the gap between the two is the
        # execution cost this run exists to measure.
        reason = rule.exit_decision(state["entry_ltp_credit"], value, due)
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

    def _book(self, done: dict, now: datetime) -> dict:
        """Writes a closed trade to the state and to the CSV, once, from its entry credit and exit fills."""
        exit_value = done["buyback_fill"]["price"] - done["sell_hedge_fill"]["price"]
        record = {
            **done,
            "exit_value_points": exit_value,
            "gross_rupees": rule.pnl_rupees(done["credit_points"], exit_value, done["quantity"]),
            "exit_time": f"{now:%Y-%m-%d %H:%M}",
        }
        self.save(record)
        append_trade(self.trades_path, record)
        return record

    def _close(self, state: dict, now: datetime) -> dict:
        """Buy the call back, then sell the hedge, through the shared exit. Records a closed trade."""
        try:
            done = super().exit(today=None)  # no expiry gate here: the rule decides the exit
        except sb.Unresolved:
            raise
        except sb.Refused:
            self._release_exit()
            raise
        status = done.get("status")
        if status == "exit_failed":
            # The buy-back was cancelled or rejected and nothing filled: the call is still held.
            return self._hold(
                self.state(),
                f"The buy-back of {state['sold']} was cancelled or rejected and nothing filled, "
                "so the sold call is still held. Nothing has been sent again.",
            )
        if status != "closed":
            if status == "short_bought_back":
                # The call is bought back, but the hedge sale was cancelled or rejected: a person decides.
                return self._hold(
                    self.state(),
                    f"The sale of {state['long']} was cancelled or rejected and nothing filled, "
                    "so the bought call is still held. Nothing has been sent again.",
                )
            return done
        record = self._book(done, now)
        self.notify(self._exit_message(record))
        return record

    def _exit_message(self, record: dict) -> str:
        """The exit alert: reason, exit value, gross, net after the charges of the four fills, cumulative net."""
        charges = row_charges(trade_row(record))
        net = record["gross_rupees"] - charges
        cumulative = ledger_total(self.trades_path)
        late = (
            "yes, it ran after the scheduled check" if record.get("exit_note") == "late" else "no"
        )
        return (
            f"{self.alert_prefix} ATM 200 closed {record['sold']} / {record['long']} on "
            f"{EXIT_NAMES.get(record['exit_reason'], record['exit_reason'])}. "
            f"Exit value {record['exit_value_points']:.2f} points, gross Rs {record['gross_rupees']:,.0f}, "
            f"net Rs {net:,.0f} after charges. Cumulative net Rs {cumulative:,.0f} from the trades file. "
            f"Late exit: {late}."
        )

    # flatten by a person --------------------------------------------------------------------
    def flatten(self, yes: bool = False) -> dict:
        """Close whatever this bot's two contracts hold, for a trade left stuck by a failure.

        Settles any lost order first, then reads the account rather than the recorded fills: buys back
        the call if it is held short, then sells the hedge if it is held long, both at market through
        the shared order code. Records FLATTENED and writes no row to trades.csv, so the result is not
        booked. A second run finds nothing in a flatten state and places nothing.
        """
        assert_india_clock()
        self.require_sandbox()
        if not yes:
            raise sb.Refused(
                "Flatten closes positions at market. Run it again with --yes to confirm."
            )
        assert_india_clock()
        self._context = "flatten"
        try:
            pending = self._reconcile(now_ist(), stop=False)
            if pending is not None:
                return pending
            return self._flatten_now()
        finally:
            self._context = None

    def _flatten_now(self) -> dict:
        state = self.state()
        if state.get("status") not in FLATTEN_STATES:
            return {"status": state.get("status", "flat")}
        sold, long = state["sold"], state["long"]
        held_sold, held_long = self._held(sold, self.strategy), self._held(long, self.strategy)
        if held_sold > 0 or held_long < 0:
            why = (
                f"{sold} or {long} is held the wrong way round for this spread, so nothing was closed. "
                "Look at the positions by hand."
            )
            self.notify(f"{self.alert_prefix} ATM 200 ALERT: {why}")
            raise sb.Refused(why)

        buy = sell = None
        if held_sold < 0:
            buy_id = self._place(sold, "BUY", -held_sold, "MARKET")
            try:
                buy = self._settle(buy_id, -held_sold)
            except sb.Unresolved as why:
                self._attention(state, why)
                raise
            if buy is None:
                self.notify(
                    f"{self.alert_prefix} ATM 200 ALERT: could not buy back {sold}. Close it by hand."
                )
                raise sb.Refused(f"The buy-back of {sold} was not filled, so nothing was sold.")
        if held_long > 0:
            if self.state().get("inflight"):
                raise sb.Refused(
                    "A short sell for this spread is still unresolved, so the hedge was not sold."
                )
            sell_id = self._place(long, "SELL", held_long, "MARKET")
            try:
                sell = self._settle(sell_id, held_long)
            except sb.Unresolved as why:
                self._attention(state, why)
                raise
            if sell is None:
                self.notify(
                    f"{self.alert_prefix} ATM 200 ALERT: could not sell {long}. Close it by hand."
                )
                raise sb.Refused(f"The sale of {long} was not filled.")

        done = {k: v for k, v in state.items() if k not in ("needs_attention", "inflight")}
        done.update(
            status=FLATTENED,
            note=FLATTEN_NOTE,
            flattened_at=f"{datetime.now():%Y-%m-%d %H:%M}",
            flatten_held={"sold": held_sold, "long": held_long},
        )
        if buy is not None:
            done["flatten_buyback_fill"] = buy.__dict__
        if sell is not None:
            done["flatten_sell_hedge_fill"] = sell.__dict__
        self.save(done)
        self.notify(
            f"{self.alert_prefix} ATM 200: flattened {sold} / {long} by hand. Nothing was booked to trades.csv."
        )
        return done
