"""The ATM 200 sandbox executor on a fake API: entry, gates, exits, failures and the trade record."""

import csv
from datetime import date, datetime

import httpx
import pytest

from services.algos import atm200_rule as rule
from services.algos import sandbox_bot as sb
from services.algos import sandbox_bot_atm200 as atm

ENTRY = date(2026, 11, 9)  # a Monday; Tuesday 10 November is the session after entry
NOW = datetime(2026, 11, 9, 10, 15)
EXPIRY = date(2026, 11, 12)  # three days after entry
SOLD = sb.contract_symbol(EXPIRY, 25000)
LONG = sb.contract_symbol(EXPIRY, 25200)
FRESH_VIX = (date(2026, 11, 6), 14.0)
QTY = sb.lot_quantity(NOW)
NEXT_1500 = datetime(2026, 11, 10, 15, 0)
ENTRY_SESSION_1100 = datetime(2026, 11, 9, 11, 0)


class FakeApi:
    def __init__(
        self,
        analyze=True,
        flip_after_check=None,
        flip_after_orders=None,
        partial_hedge=None,
        no_fill=(),
    ):
        self.analyze, self.flip_after_check = analyze, flip_after_check
        self.flip_after_orders = flip_after_orders
        self.partial_hedge, self.no_fill = partial_hedge, set(no_fill)
        self.spot = 25010.0
        self.ltp = {SOLD: 20.0, LONG: 6.0}
        self.quotes = {SOLD: (19.5, 20.5), LONG: (5.5, 6.0)}
        self.looks, self.orders, self.cancelled, self.net, self.counted = 0, {}, [], {}, set()
        self.calls = []

    def post(self, path, **p):
        self.calls.append((path, p))
        if path == "/api/v1/analyzer":
            self.looks += 1
            answer = {"status": "success", "data": {"analyze_mode": self.analyze}}
            if self.flip_after_check == self.looks:
                self.analyze = False  # Live is switched on right after this look
            return answer
        if path == "/api/v1/quotes":
            if p["symbol"] == sb.UNDERLYING:
                return {"data": {"ltp": self.spot}}
            bid, ask = self.quotes[p["symbol"]]
            return {"data": {"ltp": self.ltp[p["symbol"]], "bid": bid, "ask": ask}}
        if path == "/api/v1/placeorder":
            if p.get("sandbox_only") and not self.analyze:  # what the order service does
                return {"status": "error", "message": "analyzer mode is off"}
            oid = f"id{len(self.orders) + 1}"
            self.orders[oid] = p
            if self.flip_after_orders == len(self.orders):
                self.analyze = False  # Live is switched on right after this order
            return {"status": "success", "orderid": oid}
        if path == "/api/v1/orderstatus":
            return {"data": self._status(p["orderid"])}
        if path == "/api/v1/cancelorder":
            self.cancelled.append(p["orderid"])
            return {"status": "success"}
        if path == "/api/v1/openposition":
            return {"status": "success", "quantity": str(self.net.get(p["symbol"], 0))}
        raise AssertionError(path)

    def _status(self, oid):
        order = self.orders[oid]
        sym, action = order["symbol"], order["action"]
        qty = order["quantity"]
        if (sym, action) in self.no_fill:
            status = "cancelled" if oid in self.cancelled else "open"
            return {"order_status": status, "average_price": 0, "quantity": qty}
        if self.partial_hedge is not None and sym == LONG and action == "BUY":
            qty = self.partial_hedge
        if oid not in self.counted:
            self.counted.add(oid)
            self.net[sym] = self.net.get(sym, 0) + (qty if action == "BUY" else -qty)
        price = order["price"] or self.ltp[sym]  # a market order fills at the last price
        return {"order_status": "complete", "average_price": price, "quantity": qty}


def placed(api):
    return [c[1] for c in api.calls if c[0] == "/api/v1/placeorder"]


def bot(root, api, notes=None):
    return atm.ATM200Bot(
        api,
        root / "db" / "state.json",
        root / "db" / "trades.csv",
        notify=(notes if notes is not None else []).append,
        wait=10,
    )


def test_entry_buys_the_hedge_first_then_sells_the_call_at_the_touch(tmp_path):
    api, notes = FakeApi(), []
    state = bot(tmp_path, api, notes).enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert [(o["action"], o["symbol"], o["pricetype"], o["price"]) for o in placed(api)] == [
        ("BUY", LONG, "LIMIT", 6.0),
        ("SELL", SOLD, "LIMIT", 19.5),
    ]
    assert state["status"] == "open" and state["exit_session"] == "2026-11-10"
    assert state["quantity"] == QTY and state["credit_points"] == pytest.approx(13.5)
    assert state["entry_ltp_credit"] == pytest.approx(14.0)
    assert all(o["product"] == "NRML" and o["quantity"] == QTY for o in placed(api))
    assert all(o["strategy"] == atm.STRATEGY for o in placed(api))
    assert "opened" in notes[0]


def test_the_vix_gate_skips_at_20_and_trades_at_19_99(tmp_path):
    api, notes = FakeApi(), []
    out = bot(tmp_path / "high", api, notes).enter_spread(
        EXPIRY, NOW, set(), (date(2026, 11, 6), 20.0)
    )
    assert out["status"] == "skipped" and not placed(api) and "VIX" in notes[0]
    out = bot(tmp_path / "low", api, notes).enter_spread(
        EXPIRY, NOW, set(), (date(2026, 11, 6), 19.99)
    )
    assert out["status"] == "open" and placed(api)


def test_a_stale_or_missing_vix_does_not_skip_and_says_so(tmp_path):
    for name, latest in (("missing", None), ("old", (date(2026, 11, 3), 14.0))):
        api, notes = FakeApi(), []
        state = bot(tmp_path / name, api, notes).enter_spread(EXPIRY, NOW, set(), latest)
        assert state["status"] == "open" and state["note"] == atm.VIX_STALE_NOTE
        assert atm.VIX_STALE_NOTE in notes[0]


@pytest.mark.parametrize("expiry", [date(2026, 11, 9), date(2026, 11, 16)])
def test_an_expiry_not_one_to_six_days_away_is_skipped(tmp_path, expiry):
    api = FakeApi()
    out = bot(tmp_path, api).enter_spread(expiry, NOW, set(), FRESH_VIX)
    assert out["status"] == "skipped" and not placed(api)


def test_an_expiry_with_no_session_before_it_is_skipped(tmp_path):
    api = FakeApi()
    out = bot(tmp_path, api).enter_spread(date(2026, 11, 10), NOW, {date(2026, 11, 10)}, FRESH_VIX)
    assert out["status"] == "skipped" and not placed(api)


def test_it_never_acts_in_live_mode(tmp_path):
    api = FakeApi(analyze=False)
    with pytest.raises(sb.Refused, match="not on"):
        bot(tmp_path, api).enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert not placed(api)


def test_the_mode_is_checked_again_before_the_call_is_sold(tmp_path):
    api = FakeApi(flip_after_orders=1)  # the hedge goes in; Live is on before the call is checked
    b = bot(tmp_path, api)
    with pytest.raises(sb.Refused, match="not on"):
        b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert [o["action"] for o in placed(api)] == ["BUY"]
    assert b.state()["status"] == "orphan_hedge" and "not on" in b.state()["needs_attention"]


def test_a_refused_first_order_releases_the_entry_claim(tmp_path):
    api = FakeApi(flip_after_check=1)  # Live is on from the look before the hedge
    b = bot(tmp_path, api)
    with pytest.raises(sb.Refused):
        b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert not placed(api) and b.state()["status"] == "not_placed"


def test_a_second_entry_the_same_day_is_refused(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    with pytest.raises(sb.Refused):
        b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert len(placed(api)) == 2


def test_a_skipped_day_also_refuses_a_second_entry(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), (date(2026, 11, 6), 25.0))
    with pytest.raises(sb.Refused):
        b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert not placed(api)


def test_check_holds_when_neither_the_target_nor_the_stop_fires_even_at_1500_on_entry_day(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert b.check_spread(datetime(2026, 11, 9, 15, 0), set()) == {"status": "held", "value": 14.0}
    assert len(placed(api)) == 2


def test_the_target_closes_the_spread_buying_the_call_back_first(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    api.ltp = {SOLD: 5.0, LONG: 4.0}  # value 1.0 is at or below 31 percent of the 13.5 credit
    done = b.check_spread(ENTRY_SESSION_1100, set())
    closing = placed(api)[2:]
    assert [(o["action"], o["symbol"], o["pricetype"]) for o in closing] == [
        ("BUY", SOLD, "MARKET"),
        ("SELL", LONG, "MARKET"),
    ]
    assert done["status"] == "closed" and done["exit_reason"] == "target"
    assert done["gross_rupees"] == pytest.approx(rule.pnl_rupees(13.5, 1.0, QTY))


def test_the_stop_closes_the_spread_at_250_percent_of_the_credit(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    api.ltp = {SOLD: 40.0, LONG: 4.0}  # value 36.0 is at least 33.75
    done = b.check_spread(ENTRY_SESSION_1100, set())
    assert done["status"] == "closed" and done["exit_reason"] == "stop"
    assert done["gross_rupees"] == pytest.approx(rule.pnl_rupees(13.5, 36.0, QTY))


def test_the_time_exit_fires_only_at_the_next_sessions_1500_check(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert b.check_spread(datetime(2026, 11, 10, 14, 55), set())["status"] == "held"
    done = b.check_spread(NEXT_1500, set())
    assert done["status"] == "closed" and done["exit_reason"] == "time"
    assert done["exit_note"] == ""


def test_a_late_check_on_the_exit_session_still_exits_and_is_noted_late(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    done = b.check_spread(datetime(2026, 11, 10, 15, 20), set())
    assert done["exit_reason"] == "time" and done["exit_note"] == "late"


def test_a_check_on_a_later_day_exits_at_once_and_is_noted_late(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    done = b.check_spread(datetime(2026, 11, 11, 10, 20), set())
    assert done["status"] == "closed" and done["exit_reason"] == "time"
    assert done["exit_note"] == "late"


def test_a_partly_filled_hedge_leaves_a_state_that_needs_a_person(tmp_path):
    api = FakeApi(partial_hedge=1)
    b = bot(tmp_path, api)
    with pytest.raises(sb.Unresolved, match="filled 1 of"):
        b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    state = b.state()
    assert state["status"] == "orphan_hedge" and "filled 1 of" in state["needs_attention"]
    assert b.check_spread(ENTRY_SESSION_1100, set())["status"] == "needs_attention"
    assert [o["action"] for o in placed(api)] == ["BUY"]  # nothing further is placed


def test_an_unfilled_hedge_records_no_position_and_sells_no_call(tmp_path):
    api = FakeApi(no_fill=[(LONG, "BUY")])
    b = bot(tmp_path, api)
    state = b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert state["status"] == "no_hedge" and api.cancelled == ["id1"]
    assert [o["action"] for o in placed(api)] == ["BUY"]


def test_dry_run_places_nothing_for_entry_or_check(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    out = b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX, dry_run=True)
    assert out["status"] == "dry_run" and out["sold"] == SOLD
    assert not placed(api) and not (tmp_path / "db" / "state.json").exists()
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    api.ltp = {SOLD: 5.0, LONG: 4.0}
    assert b.check_spread(ENTRY_SESSION_1100, set(), dry_run=True)["status"] == "dry_run"
    assert len(placed(api)) == 2 and b.state()["status"] == "open"


def test_every_order_the_bot_sends_carries_sandbox_only(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    api.ltp = {SOLD: 5.0, LONG: 4.0}
    b.check_spread(ENTRY_SESSION_1100, set())
    sent = placed(api)
    assert len(sent) == 4 and all(o["sandbox_only"] is True for o in sent)


def test_a_closed_trade_is_written_once_to_the_csv(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    api.ltp = {SOLD: 5.0, LONG: 4.0}
    b.check_spread(ENTRY_SESSION_1100, set())
    assert b.check_spread(NEXT_1500, set())["status"] == "closed"
    with (tmp_path / "db" / "trades.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1 and rows[0]["exit_reason"] == "target" and rows[0]["sold"] == SOLD


def test_the_exit_thresholds_use_the_ltp_credit_at_entry_not_the_fill_credit(tmp_path):
    """The replay and the compared LTP value share one basis; fills only decide the booked result."""
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    state = b.state()
    ltp_credit = state["entry_ltp_credit"]
    # make the fill credit very different from the LTP credit, as a bad fill would
    state["credit_points"] = ltp_credit + 30.0
    b.save(state)
    # a value just over 250 percent of the LTP credit but far under 250 percent of the inflated fill credit
    value = rule.STOP * ltp_credit + 0.5
    api.ltp = {SOLD: value + 4.0, LONG: 4.0}
    done = b.check_spread(ENTRY_SESSION_1100, set())
    assert done["status"] == "closed" and done["exit_reason"] == "stop"


# ledger stop, S3n collision, flatten, and failures at each order ------------------------------
FOLLOW_UP = datetime(2026, 11, 9, 10, 20)  # the first 5-minute check after the entry
ENTRY_POINTS = {  # (when in the call, action, symbol): the failure is raised there
    "hedge_sent": ("sent", "BUY", LONG),
    "hedge_fill_awaited": ("poll", "BUY", LONG),
    "short_sent": ("sent", "SELL", SOLD),
    "short_fill_awaited": ("poll", "SELL", SOLD),
}
EXIT_POINTS = {
    "buyback_sent": ("sent", "BUY", SOLD),
    "sellhedge_sent": ("sent", "SELL", LONG),
}
FAILURES = ["timeout", "interrupt"]


def failure(kind):
    """A timeout as the HTTP client raises it, or a Ctrl-C or kill that lands in the same place."""
    if kind == "timeout":
        return httpx.TimeoutException("the broker did not answer")
    return KeyboardInterrupt()


class BrokerFake:
    """A broker book: a sent order fills at once unless its (action, symbol) is pending, and positions
    follow the fills. One failure can be armed at a point in the sequence and fires once."""

    def __init__(self, pending=()):
        self.analyze = True
        self.ltp = {SOLD: 20.0, LONG: 6.0}
        self.quotes = {SOLD: (19.5, 20.5), LONG: (5.5, 6.0)}
        self.pending, self.crash = set(pending), None
        self.orders, self.calls, self.extra = {}, [], {}

    def arm(self, when, action, symbol, exc):
        self.crash = (when, action, symbol, exc)

    def _maybe_crash(self, when, action, symbol):
        if self.crash and self.crash[:3] == (when, action, symbol):
            exc, self.crash = self.crash[3], None
            raise exc

    def held(self, symbol):
        total = 0
        for order in self.orders.values():
            p = order["p"]
            if order["status"] == "complete" and p["symbol"] == symbol:
                total += p["quantity"] if p["action"] == "BUY" else -p["quantity"]
        return total

    def fill_pending(self, action, symbol):
        for order in self.orders.values():
            p = order["p"]
            if order["status"] == "open" and (p["action"], p["symbol"]) == (action, symbol):
                order["status"] = "complete"

    def post(self, path, **p):
        self.calls.append((path, p))
        if path == "/api/v1/analyzer":
            return {"status": "success", "data": {"analyze_mode": self.analyze}}
        if path == "/api/v1/quotes":
            if p["symbol"] == sb.UNDERLYING:
                return {"data": {"ltp": 25010.0}}
            bid, ask = self.quotes[p["symbol"]]
            return {"data": {"ltp": self.ltp[p["symbol"]], "bid": bid, "ask": ask}}
        if path == "/api/v1/placeorder":
            if p.get("sandbox_only") and not self.analyze:
                return {"status": "error", "message": "analyzer mode is off"}
            oid = f"id{len(self.orders) + 1}"
            status = "open" if (p["action"], p["symbol"]) in self.pending else "complete"
            price = p["price"] or self.ltp[p["symbol"]]  # a market order fills at the last price
            self.orders[oid] = {"p": p, "status": status, "price": price}
            self._maybe_crash("sent", p["action"], p["symbol"])
            return {"status": "success", "orderid": oid}
        if path == "/api/v1/orderstatus":
            order = self.orders[p["orderid"]]
            self._maybe_crash("poll", order["p"]["action"], order["p"]["symbol"])
            return {
                "data": {
                    "order_status": order["status"],
                    "average_price": order["price"],
                    "quantity": order["p"]["quantity"],
                }
            }
        if path == "/api/v1/cancelorder":
            order = self.orders[p["orderid"]]
            if order["status"] == "open":
                order["status"] = "cancelled"
            return {"status": "success"}
        if path == "/api/v1/openposition":
            label_held = self.held(p["symbol"]) if p["strategy"] == atm.STRATEGY else 0
            other = self.extra.get((p["strategy"], p["symbol"]), 0)
            return {"status": "success", "quantity": str(label_held + other)}
        raise AssertionError(path)


def naked_short(api):
    """A short call with less long call held against it than the short."""
    short = api.held(SOLD)
    return short < 0 and api.held(LONG) < -short


def no_repeats(api):
    """No two orders in the run share a side and a symbol."""
    sent = [(o["action"], o["symbol"]) for o in placed(api)]
    return len(sent) == len(set(sent))


def open_spread(root, api, notes):
    b = bot(root, api, notes)
    b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    api.ltp = {SOLD: 5.0, LONG: 4.0}  # spread value 1.0 is at or below the target: an exit is due
    return b


@pytest.mark.parametrize("kind", FAILURES)
@pytest.mark.parametrize("point", list(ENTRY_POINTS))
def test_a_failure_during_entry_leaves_a_state_that_needs_a_person(tmp_path, point, kind):
    api, notes = BrokerFake(), []
    when, action, symbol = ENTRY_POINTS[point]
    api.arm(when, action, symbol, failure(kind))
    b = bot(tmp_path, api, notes)
    with pytest.raises(type(failure(kind))):
        b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    sent_before, notes = len(placed(api)), []
    b.notify = notes.append
    out = b.check_spread(FOLLOW_UP, set())
    assert out["status"] == "needs_attention"
    assert len(notes) == 1 and "ALERT" in notes[0]  # exactly one alert for the unclear state
    assert len(placed(api)) == sent_before  # the follow-up sends nothing
    assert no_repeats(api) and not naked_short(api)


@pytest.mark.parametrize("kind", FAILURES)
@pytest.mark.parametrize("point", list(EXIT_POINTS))
def test_a_failure_during_exit_leaves_a_safe_state_and_no_new_order(tmp_path, point, kind):
    api, notes = BrokerFake(), []
    b = open_spread(tmp_path, api, notes)
    when, action, symbol = EXIT_POINTS[point]
    api.arm(when, action, symbol, failure(kind))
    with pytest.raises(type(failure(kind))):
        b.check_spread(ENTRY_SESSION_1100, set())
    sent_before, notes = len(placed(api)), []
    b.notify = notes.append
    out = b.check_spread(ENTRY_SESSION_1100, set())
    assert out["status"] == "mismatch"  # the book no longer matches the recorded legs
    assert len(notes) == 1 and "ALERT" in notes[0]
    assert len(placed(api)) == sent_before
    assert no_repeats(api) and not naked_short(api)


@pytest.mark.xfail(
    strict=True,
    reason="GAP: a buy-back or sell-hedge accepted but not yet filled when the reply is lost is not "
    "seen by the follow-up check, which then sends the same order again. Needs an in-flight order "
    "check before the exit is re-sent.",
)
@pytest.mark.parametrize("point", list(EXIT_POINTS))
def test_an_exit_order_still_working_is_not_sent_again(tmp_path, point):
    when, action, symbol = EXIT_POINTS[point]
    api, notes = BrokerFake(pending={(action, symbol)}), []
    b = open_spread(tmp_path, api, notes)
    api.arm(when, action, symbol, httpx.TimeoutException("the broker did not answer"))
    with pytest.raises(httpx.TimeoutException):
        b.check_spread(ENTRY_SESSION_1100, set())
    b.check_spread(ENTRY_SESSION_1100, set())
    assert no_repeats(api)


@pytest.mark.xfail(
    strict=True,
    reason="GAP: a short sell lost in flight can still be working. Flatten sells the hedge and cannot "
    "see or cancel the short, so when it fills the spread is a naked short. The order id is not kept.",
)
def test_a_working_short_sell_cannot_fill_naked_after_a_flatten(tmp_path):
    api = BrokerFake(pending={("SELL", SOLD)})
    api.arm("sent", "SELL", SOLD, httpx.TimeoutException("the broker did not answer"))
    b = bot(tmp_path, api, [])
    with pytest.raises(httpx.TimeoutException):
        b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    b.flatten(yes=True)
    api.fill_pending("SELL", SOLD)
    assert not naked_short(api)


def test_a_lost_hedge_reply_then_flatten_sells_only_the_hedge(tmp_path):
    api = BrokerFake()
    api.arm("sent", "BUY", LONG, httpx.TimeoutException("the broker did not answer"))
    b = bot(tmp_path, api, [])
    with pytest.raises(httpx.TimeoutException):
        b.enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    sent = len(placed(api))
    b.flatten(yes=True)
    assert [(o["action"], o["symbol"]) for o in placed(api)[sent:]] == [("SELL", LONG)]
    assert b.state()["status"] == atm.FLATTENED


def test_flatten_refuses_without_yes_and_places_nothing(tmp_path):
    api = BrokerFake()
    b = open_spread(tmp_path, api, [])
    sent = len(placed(api))
    with pytest.raises(sb.Refused, match="--yes"):
        b.flatten(yes=False)
    assert len(placed(api)) == sent and b.state()["status"] == "open"


def test_flatten_refuses_in_live_mode(tmp_path):
    api = BrokerFake()
    b = open_spread(tmp_path, api, [])
    api.analyze = False
    sent = len(placed(api))
    with pytest.raises(sb.Refused, match="not on"):
        b.flatten(yes=True)
    assert len(placed(api)) == sent


def test_flatten_buys_back_the_call_then_sells_the_hedge_and_books_nothing(tmp_path):
    api = BrokerFake()
    b = open_spread(tmp_path, api, [])
    sent = len(placed(api))
    done = b.flatten(yes=True)
    closing = placed(api)[sent:]
    assert [(o["action"], o["symbol"], o["pricetype"]) for o in closing] == [
        ("BUY", SOLD, "MARKET"),
        ("SELL", LONG, "MARKET"),
    ]
    assert all(o["sandbox_only"] is True for o in closing)
    assert done["status"] == atm.FLATTENED and b.state()["status"] == atm.FLATTENED
    assert api.held(SOLD) == 0 and api.held(LONG) == 0
    assert not (tmp_path / "db" / "trades.csv").exists()


def test_flatten_a_second_time_does_nothing(tmp_path):
    api = BrokerFake()
    b = open_spread(tmp_path, api, [])
    b.flatten(yes=True)
    sent = len(placed(api))
    again = b.flatten(yes=True)
    assert again["status"] == atm.FLATTENED and len(placed(api)) == sent


def test_flatten_of_a_recorded_entry_with_nothing_held_places_nothing(tmp_path):
    api = BrokerFake()
    b = bot(tmp_path, api, [])
    b.save({"status": "entering", "sold": SOLD, "long": LONG, "quantity": QTY})
    b.flatten(yes=True)
    assert not placed(api) and b.state()["status"] == atm.FLATTENED


def test_entry_is_refused_once_the_ledger_has_lost_20000(tmp_path):
    trades = tmp_path / "db" / "trades.csv"
    atm.append_trade(trades, {"entry_date": "2026-10-01", "sold": "A", "gross_rupees": -12000})
    atm.append_trade(trades, {"entry_date": "2026-10-02", "sold": "B", "gross_rupees": -8000})
    api, notes = FakeApi(), []
    with pytest.raises(sb.Refused) as why:
        bot(tmp_path, api, notes).enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert str(why.value) == atm.LEDGER_STOP_MESSAGE
    assert "lost 20,000" in notes[0] and not placed(api)


def test_entry_goes_ahead_at_19999_lost_and_ignores_blank_rows(tmp_path):
    trades = tmp_path / "db" / "trades.csv"
    atm.append_trade(trades, {"entry_date": "2026-10-01", "sold": "A", "gross_rupees": -12000})
    atm.append_trade(trades, {"entry_date": "2026-10-02", "sold": "B", "gross_rupees": -7999})
    atm.append_trade(trades, {"entry_date": "2026-10-03", "sold": "C"})  # no figure: counts as 0
    state = bot(tmp_path, FakeApi(), []).enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert state["status"] == "open"


@pytest.mark.parametrize("label", [sb.STRATEGY, atm.STRATEGY])
@pytest.mark.parametrize("symbol", [SOLD, LONG])
def test_a_contract_already_held_refuses_entry_and_names_it(tmp_path, label, symbol):
    api, notes = BrokerFake(), []
    api.extra[(label, symbol)] = QTY
    with pytest.raises(sb.Refused, match=symbol):
        bot(tmp_path, api, notes).enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    assert not placed(api) and symbol in notes[0]


def test_the_s3n_lookup_is_sent_with_the_s3n_label_and_this_bots_label_too(tmp_path):
    api = BrokerFake()
    bot(tmp_path, api, []).enter_spread(EXPIRY, NOW, set(), FRESH_VIX)
    lookups = {
        (p["symbol"], p["strategy"]) for path, p in api.calls if path == "/api/v1/openposition"
    }
    assert {
        (SOLD, sb.STRATEGY),
        (LONG, sb.STRATEGY),
        (SOLD, atm.STRATEGY),
        (LONG, atm.STRATEGY),
    } <= lookups
