"""Sandbox-mode executor of the weekly call spread (S3n), run beside the forward shadow ledger.

The ledger tests the idea on stored candles; this bot tests whether the orders would actually fill:
it places the same two legs through the OpenAlgo API, hedge first, and records the fills so they
can be compared with the ledger week by week. It refuses to place anything unless analyzer
(sandbox) mode is on, never places more than one lot, and never sells the call unless the bought
call is filled. The decision rules are the registered ones in forward_shadow.REGISTERED.

The order logic takes an injected ``client`` (anything with ``post(path, **payload) -> dict``), a
``sleep`` and a ``notify`` so it runs in tests with no network and no clock.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from services.algos import forward_shadow as fs
from services.algos import intraday

UNDERLYING = "NIFTY"
EXCHANGE = "NFO"
PRODUCT = "NRML"  # a spread held to expiry across sessions; MIS would be squared off the same day
STRATEGY = "S3n-sandbox"
WIDTH = 100
SESSIONS_BEFORE = 2
STRIKE_STEP = 50
FILL_WAIT_SECONDS = 60
MAX_LOTS = 1
#: Recorded states in which something is still held, so a new entry is refused.
ACTIVE = ("open", "orphan_hedge", "short_bought_back")


class Refused(Exception):
    """The bot declines to act; the message is written for the trader."""


class Unresolved(Refused):
    """An order's state cannot be told (still open after the cancel, or only partly filled). Nothing
    further is placed until the trader has looked."""


def contract_symbol(expiry: date, strike: float, kind: str = "CE") -> str:
    return f"{UNDERLYING}{expiry:%d%b%y}".upper() + f"{int(strike)}{kind}"


def entry_day(expiry: date, holidays: set[date], sessions_before: int = SESSIONS_BEFORE) -> date:
    """The session ``sessions_before`` trading days before ``expiry`` (weekends and holidays skipped)."""
    day, left = expiry, sessions_before
    while left:
        day -= timedelta(days=1)
        if day.weekday() < 5 and day not in holidays:
            left -= 1
    return day


def strikes(spot: float, width: int = WIDTH) -> tuple[int, int]:
    sold = int(round(spot / STRIKE_STEP) * STRIKE_STEP)
    return sold, sold + width


def should_enter(spot: float, previous_close: float, vix_previous_close: float) -> tuple[bool, str]:
    """The registered filters: VIX the evening before below the ceiling, no gap down of 1 percent."""
    rules = fs.REGISTERED
    if vix_previous_close >= rules.vix_ceiling:
        return (
            False,
            f"India VIX closed at {vix_previous_close:.1f}, at or above {rules.vix_ceiling:.0f}",
        )
    if spot / previous_close - 1 <= rules.gap_floor:
        return False, "the Nifty is 1 percent or more below the previous close"
    return True, "filters passed"


def limit_prices(sold_quote: dict, long_quote: dict) -> tuple[float, float]:
    """(price to sell the call at, price to buy the hedge at): the touch, never a made-up price."""
    sell = float(sold_quote.get("bid") or 0)
    buy = float(long_quote.get("ask") or 0)
    if sell <= 0 or buy <= 0:
        raise Refused(
            "There is no bid or ask on one of the two options right now, so no order was placed."
        )
    if sell - buy <= 0:
        raise Refused(
            "The two options would not give a credit at today's bid and ask, so no order was placed."
        )
    return sell, buy


def lot_quantity(on: date | datetime) -> int:
    return intraday.lot_size_for(on) * MAX_LOTS


@dataclass
class Fill:
    orderid: str
    price: float
    quantity: int


class Bot:
    def __init__(
        self,
        client: Any,
        state_path: Path,
        notify: Callable[[str], Any] = print,
        sleep: Callable[[float], None] = lambda s: None,
        wait: int = FILL_WAIT_SECONDS,
    ):
        self.client, self.path, self.notify, self.sleep, self.wait = (
            client,
            state_path,
            notify,
            sleep,
            wait,
        )

    # state ----------------------------------------------------------------------------------
    def state(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {}

    def save(self, state: dict) -> None:
        """Write the state in one step, so a crash never leaves half a file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(json.dumps(state, indent=2, default=str))
        os.replace(name, self.path)

    # guards ---------------------------------------------------------------------------------
    def require_sandbox(self) -> None:
        reply = self.client.post("/api/v1/analyzer")
        if not (
            reply.get("status") == "success" and reply.get("data", {}).get("analyze_mode") is True
        ):
            raise Refused(
                "Analyzer (sandbox) mode is not on, so the bot placed nothing. Switch OpenAlgo to "
                "analyzer mode first; this bot never trades live."
            )

    # orders ---------------------------------------------------------------------------------
    def _place(
        self, symbol: str, action: str, quantity: int, pricetype: str, price: float = 0.0
    ) -> str:
        # Asked again before EVERY order: the toggle can be switched between two orders, and the
        # order endpoint follows whatever it says when the order arrives.
        self.require_sandbox()
        reply = self.client.post(
            "/api/v1/placeorder", strategy=STRATEGY, exchange=EXCHANGE, symbol=symbol,
            action=action, quantity=quantity, pricetype=pricetype, product=PRODUCT, price=price,
            sandbox_only=True,  # the order service refuses it unless analyzer mode is on, in one step
        )  # fmt: skip
        if reply.get("status") != "success" or not reply.get("orderid"):
            raise Refused(
                f"The order for {symbol} was not accepted: {reply.get('message', 'no reason given')}"
            )
        return str(reply["orderid"])

    def _filled(self, orderid: str) -> Fill | None:
        waited = 0
        while True:
            data = self.client.post("/api/v1/orderstatus", strategy=STRATEGY, orderid=orderid).get(
                "data", {}
            )
            status = str(data.get("order_status", "")).lower()
            if status == "complete":
                return Fill(
                    orderid,
                    float(data.get("average_price") or 0),
                    int(float(data.get("quantity") or 0)),
                )
            if status in ("rejected", "cancelled") or waited >= self.wait:
                return None
            self.sleep(5)
            waited += 5

    def _settle(self, orderid: str, quantity: int) -> Fill | None:
        """Wait for a fill. If none comes, cancel and look once more: an order can fill in the moment
        between the last look and the cancel, and then the position exists and must be recorded.

        Returns the full fill, or None only when the order is certainly not filled (rejected or
        cancelled). An order still open after the cancel, or filled in part, raises Unresolved: it
        may hold a position, and treating it as nothing is how a leg is left unwatched."""
        fill = self._filled(orderid)
        if fill is None:
            self._cancel(orderid)
            data = self.client.post("/api/v1/orderstatus", strategy=STRATEGY, orderid=orderid).get(
                "data", {}
            )
            status = str(data.get("order_status", "")).lower()
            if status == "complete":
                fill = Fill(
                    orderid,
                    float(data.get("average_price") or 0),
                    int(float(data.get("quantity") or 0)),
                )
            elif status in ("rejected", "cancelled"):
                return None
            else:
                raise Unresolved(
                    f"Order {orderid} is still {status or 'of unknown state'} after the cancel."
                )
        if fill.quantity < quantity:
            raise Unresolved(f"Order {orderid} filled {fill.quantity} of {quantity}.")
        return fill

    def _attention(self, state: dict, why: Exception) -> None:
        """Record that something needs a person, and say so. Nothing new is placed meanwhile."""
        self.save({**state, "needs_attention": str(why)})
        self.notify(f"Sandbox bot ALERT: {why} Look at the positions and the order book now.")

    def _cancel(self, orderid: str) -> None:
        self.client.post("/api/v1/cancelorder", strategy=STRATEGY, orderid=orderid)

    def quote(self, symbol: str, exchange: str = EXCHANGE) -> dict:
        return self.client.post("/api/v1/quotes", symbol=symbol, exchange=exchange).get("data", {})

    def previous_close(self, symbol: str, exchange: str, today: date) -> float:
        """Close of the last daily bar before ``today``. The index quote's own previous close is
        returned as 0 by the broker feed, so the daily history is the source."""
        reply = self.client.post(
            "/api/v1/history", symbol=symbol, exchange=exchange, interval="D",
            start_date=f"{today - timedelta(days=12):%Y-%m-%d}", end_date=f"{today:%Y-%m-%d}",
        )  # fmt: skip
        earlier = [
            (datetime.fromtimestamp(row["timestamp"], UTC).date(), float(row["close"]))
            for row in reply.get("data") or []
            if datetime.fromtimestamp(row["timestamp"], UTC).date() < today
        ]
        return max(earlier)[1] if earlier else 0.0

    # actions --------------------------------------------------------------------------------
    def enter(
        self, expiry: date, now: datetime, holidays: set[date], dry_run: bool = False
    ) -> dict:
        """Open the spread if today is the entry session, the filters pass and nothing is open."""
        self.require_sandbox()
        today = now.date()
        if state := self.state():
            if state.get("status") in ACTIVE:
                raise Refused(
                    f"A spread is already recorded ({state.get('status')}); nothing new was placed."
                )
        if today != entry_day(expiry, holidays):
            raise Refused(f"Today is not the entry session for the {expiry:%d %b %Y} expiry.")
        spot = float(self.quote(UNDERLYING, "NSE_INDEX").get("ltp") or 0)
        prev = self.previous_close(UNDERLYING, "NSE_INDEX", today)
        vix_prev = self.previous_close("INDIAVIX", "NSE_INDEX", today)
        if not (spot and prev and vix_prev):
            raise Refused("The Nifty or India VIX quote is missing, so no order was placed.")
        ok, why = should_enter(spot, prev, vix_prev)
        if not ok:
            self.notify(f"Sandbox bot: no entry for the {expiry:%d %b} expiry, {why}.")
            return {"status": "skipped", "reason": why}
        sold_k, long_k = strikes(spot)
        sold_sym, long_sym = contract_symbol(expiry, sold_k), contract_symbol(expiry, long_k)
        sell_at, buy_at = limit_prices(self.quote(sold_sym), self.quote(long_sym))
        qty = lot_quantity(now)
        plan = {"expiry": f"{expiry:%Y-%m-%d}", "sold": sold_sym, "long": long_sym, "quantity": qty,
                "sell_at": sell_at, "buy_at": buy_at, "entry_time": f"{now:%Y-%m-%d %H:%M}"}  # fmt: skip
        if dry_run:
            return {"status": "dry_run", **plan}
        hedge_id = self._place(long_sym, "BUY", qty, "LIMIT", buy_at)
        try:
            hedge = self._settle(hedge_id, qty)
        except Unresolved as why:
            self._attention({**plan, "status": "orphan_hedge"}, why)
            raise
        if hedge is None:
            self.notify(
                f"Sandbox bot: the hedge {long_sym} did not fill, so the call was not sold. Nothing is open."
            )
            return {"status": "no_hedge", **plan}
        # The hedge is held from here on: record it before anything else can go wrong.
        state = {**plan, "status": "orphan_hedge", "hedge_fill": hedge.__dict__}
        self.save(state)
        try:
            short_id = self._place(sold_sym, "SELL", qty, "LIMIT", sell_at)
        except Refused as why:
            self.notify(
                f"Sandbox bot: the hedge {long_sym} is held but the call {sold_sym} was not placed "
                f"({why}). Only the bought call is held; close it with the exit command."
            )
            raise
        try:
            short = self._settle(short_id, qty)
        except Unresolved as why:
            self._attention(state, why)
            raise
        if short is None:
            self.notify(
                f"Sandbox bot: the hedge {long_sym} filled but the call {sold_sym} did not. Only the "
                "bought call is held; close it with the exit command."
            )
            return state
        state = {
            **plan,
            "status": "open",
            "hedge_fill": hedge.__dict__,
            "short_fill": short.__dict__,
        }
        self.save(state)
        credit = short.price - hedge.price
        self.notify(
            f"Sandbox bot: opened {sold_sym} / {long_sym}, {qty} qty, credit {credit:.2f} points "
            f"(limits {sell_at:.2f} / {buy_at:.2f})."
        )
        return state

    def check(self) -> dict:
        """Both legs must be held. A sold call without its hedge is the failure that matters."""
        self.require_sandbox()
        state = self.state()
        if state.get("status") not in ACTIVE:
            return {"status": state.get("status", "flat")}
        held = {}
        for key in ("sold", "long"):
            reply = self.client.post(
                "/api/v1/openposition",
                strategy=STRATEGY,
                symbol=state[key],
                exchange=EXCHANGE,
                product=PRODUCT,
            )
            held[key] = int(float(reply.get("quantity") or 0))
        qty = state["quantity"]
        expected_sold = -qty if state["status"] == "open" else 0  # the call is held only when open
        if held["sold"] == expected_sold and held["long"] == qty:
            return {"status": "ok", "held": held}
        self.notify(
            f"Sandbox bot ALERT: expected {state['sold']} at {expected_sold} and {state['long']} at +{qty}, "
            f"found {held['sold']} and {held['long']}. Look at the positions now."
        )
        return {"status": "mismatch", "held": held}

    def exit(self, dry_run: bool = False, today: date | None = None, force: bool = False) -> dict:
        """Close both legs, buying the call back first. Market orders: leaving is the priority."""
        self.require_sandbox()
        state = self.state()
        if state.get("status") not in ACTIVE:
            raise Refused("No spread is recorded as open, so there is nothing to close.")
        if not force and today is not None and today < date.fromisoformat(state["expiry"]):
            raise Refused(
                f"The spread runs to the {state['expiry']} expiry session, so it was not closed today. "
                "Use --force only to close it early by hand."
            )
        if dry_run:
            return {"status": "dry_run", "would_close": state["status"]}
        qty, closed = state["quantity"], {}
        if state["status"] == "open":
            buy_id = self._place(state["sold"], "BUY", qty, "MARKET")
            try:
                buy = self._settle(buy_id, qty)
            except Unresolved as why:
                self._attention(state, why)
                raise
            if buy is None:
                self.notify(
                    f"Sandbox bot ALERT: could not buy back {state['sold']}. Close it by hand."
                )
                return {**state, "status": "exit_failed"}
            closed["buyback_fill"] = buy.__dict__
            # The call is closed: record it before the hedge is sold, so a retry never buys it twice.
            state = {**state, **closed, "status": "short_bought_back"}
            self.save(state)
        elif state["status"] == "short_bought_back":
            closed["buyback_fill"] = state["buyback_fill"]
        sell_id = self._place(state["long"], "SELL", qty, "MARKET")
        try:
            sell = self._settle(sell_id, qty)
        except Unresolved as why:
            self._attention(state, why)
            raise
        if sell is None:
            self.notify(f"Sandbox bot ALERT: could not sell {state['long']}. Close it by hand.")
            return {**state, **closed, "status": "short_bought_back"}
        closed["sell_hedge_fill"] = sell.__dict__
        done = {
            **state,
            **closed,
            "status": "closed",
            "exit_time": f"{datetime.now():%Y-%m-%d %H:%M}",
        }
        self.save(done)
        self.notify(f"Sandbox bot: closed {state['sold']} / {state['long']}.")
        return done


def compare(state: dict, ledger_trade: dict) -> dict[str, float]:
    """Bot fills against the ledger's candle fills for the same week, in points (positive = bot did worse)."""
    short, hedge = state["short_fill"]["price"], state["hedge_fill"]["price"]
    bot_credit = short - hedge
    out = {"ledger_credit": float(ledger_trade["credit"]), "bot_credit": bot_credit}
    out["entry_shortfall"] = out["ledger_credit"] - bot_credit
    if "buyback_fill" in state and "sell_hedge_fill" in state:
        bot_exit = state["buyback_fill"]["price"] - state["sell_hedge_fill"]["price"]
        out["ledger_exit_value"] = float(ledger_trade["exit_value"])
        out["bot_exit_value"] = bot_exit
        out["exit_shortfall"] = bot_exit - out["ledger_exit_value"]
    return out
