"""The ATM 200 sandbox executor on a fake API: entry, gates, exits, failures and the trade record."""

import csv
from datetime import date, datetime

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
