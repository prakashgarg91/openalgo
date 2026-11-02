"""The sandbox-mode executor on a fake API: guards, order sequence, failures and the comparison."""

from datetime import UTC, date, datetime

import pytest

from services.algos import sandbox_bot as sb

EXPIRY = date(2026, 11, 10)
NOW = datetime(2026, 11, 6, 10, 15)


class FakeApi:
    def __init__(
        self,
        analyze=True,
        fill_hedge=True,
        fill_short=True,
        vix=14.0,
        spot=25010.0,
        positions=None,
        flip_after_orders=None,
        fill_buyback=True,
        fill_after_cancel=False,
    ):
        self.analyze, self.vix, self.spot = analyze, vix, spot
        self.flip_after_orders, self.fill_buyback = flip_after_orders, fill_buyback
        self.fill_after_cancel = fill_after_cancel
        self.fill = {"hedge": fill_hedge, "short": fill_short}
        self.calls, self.orders, self.cancelled = [], {}, []
        self.positions = positions or {}

    def post(self, path, **p):
        self.calls.append((path, p))
        if path == "/api/v1/analyzer":
            return {"status": "success", "data": {"analyze_mode": self.analyze}}
        if path == "/api/v1/quotes":
            if p["symbol"] == "NIFTY":
                return {"data": {"ltp": self.spot, "prev_close": 0}}  # the real feed returns 0 here
            if p["symbol"] == "INDIAVIX":
                return {"data": {"ltp": 15.0, "prev_close": 0}}
            ask, bid = (6.0, 5.5) if p["symbol"].endswith("25100CE") else (20.5, 20.0)
            return {"data": {"bid": bid, "ask": ask}}
        if path == "/api/v1/history":
            close = 25000.0 if p["symbol"] == "NIFTY" else self.vix
            day = lambda d: int(datetime(2026, 11, d, tzinfo=UTC).timestamp())  # noqa: E731
            return {
                "data": [{"timestamp": day(5), "close": close}, {"timestamp": day(6), "close": 1.0}]
            }
        if path == "/api/v1/placeorder":
            oid = f"id{len(self.orders) + 1}"
            self.orders[oid] = p
            if self.flip_after_orders is not None and len(self.orders) >= self.flip_after_orders:
                self.analyze = False  # the owner switches to Live right after this order
            return {"status": "success", "orderid": oid}
        if path == "/api/v1/orderstatus":
            order = self.orders[p["orderid"]]
            hedge = order["action"] == "BUY" and order["symbol"].endswith("25100CE")
            buyback = order["action"] == "BUY" and order["symbol"].endswith("25000CE")
            ok = (
                self.fill_buyback
                if buyback
                else self.fill["hedge"]
                if hedge
                else self.fill["short"]
                if order["action"] == "SELL" and order["symbol"].endswith("25000CE")
                else True
            )
            price = order["price"] or (20.2 if order["action"] == "BUY" else 5.4)
            if self.fill_after_cancel and p["orderid"] in self.cancelled:
                ok = True  # it filled in the moment between the last look and the cancel
            return {
                "data": {
                    "order_status": "complete" if ok else "open",
                    "average_price": price,
                    "quantity": order["quantity"],
                }
            }
        if path == "/api/v1/cancelorder":
            self.cancelled.append(p["orderid"])
            return {"status": "success"}
        if path == "/api/v1/openposition":
            return {"status": "success", "quantity": str(self.positions.get(p["symbol"], 0))}
        raise AssertionError(path)


def bot(tmp_path, api, notes=None):
    return sb.Bot(
        api, tmp_path / "state.json", notify=(notes if notes is not None else []).append, wait=10
    )


def test_entry_day_skips_weekends_and_holidays():
    assert sb.entry_day(EXPIRY, set()) == date(
        2026, 11, 6
    )  # Tue expiry: Fri is two sessions before
    assert sb.entry_day(EXPIRY, {date(2026, 11, 9)}) == date(2026, 11, 5)


def test_symbols_and_strikes():
    assert sb.contract_symbol(EXPIRY, 25000) == "NIFTY10NOV2625000CE"
    assert sb.strikes(25010.0) == (25000, 25100)
    assert sb.strikes(25030.0) == (25050, 25150)


def test_filters_are_the_registered_ones():
    assert sb.should_enter(25010, 25000, 14.0)[0]
    assert not sb.should_enter(25010, 25000, 20.0)[0]
    assert not sb.should_enter(24740, 25000, 14.0)[0]


def test_it_never_acts_unless_analyzer_mode_is_on(tmp_path):
    api = FakeApi(analyze=False)
    with pytest.raises(sb.Refused, match="never trades live"):
        bot(tmp_path, api).enter(EXPIRY, NOW, set())
    assert not [c for c in api.calls if c[0] == "/api/v1/placeorder"]


def test_entry_buys_the_hedge_first_then_sells_the_call_at_the_touch(tmp_path):
    api, notes = FakeApi(), []
    state = bot(tmp_path, api, notes).enter(EXPIRY, NOW, set())
    placed = [c[1] for c in api.calls if c[0] == "/api/v1/placeorder"]
    assert [(o["action"], o["symbol"], o["pricetype"], o["price"]) for o in placed] == [
        ("BUY", "NIFTY10NOV2625100CE", "LIMIT", 6.0),
        ("SELL", "NIFTY10NOV2625000CE", "LIMIT", 20.0),
    ]
    assert all(o["quantity"] == 65 and o["product"] == "NRML" for o in placed)
    assert state["status"] == "open" and notes and "credit 14.00" in notes[0]


def test_a_second_entry_while_open_is_refused(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter(EXPIRY, NOW, set())
    with pytest.raises(sb.Refused, match="already recorded"):
        b.enter(EXPIRY, NOW, set())


def test_the_call_is_never_sold_when_the_hedge_does_not_fill(tmp_path):
    api, notes = FakeApi(fill_hedge=False), []
    state = bot(tmp_path, api, notes).enter(EXPIRY, NOW, set())
    assert state["status"] == "no_hedge" and api.cancelled == ["id1"]
    assert [c[1]["action"] for c in api.calls if c[0] == "/api/v1/placeorder"] == ["BUY"]
    assert not (tmp_path / "state.json").exists()


def test_an_unfilled_call_leaves_a_recorded_orphan_hedge(tmp_path):
    api, notes = FakeApi(fill_short=False), []
    state = bot(tmp_path, api, notes).enter(EXPIRY, NOW, set())
    assert state["status"] == "orphan_hedge" and "id2" in api.cancelled
    assert "close it" in notes[0]


def test_filters_stop_an_entry_without_orders(tmp_path):
    api, notes = FakeApi(vix=25.0), []
    out = bot(tmp_path, api, notes).enter(EXPIRY, NOW, set())
    assert out["status"] == "skipped" and not api.orders and "VIX" in notes[0]


def test_wrong_day_and_dry_run_place_nothing(tmp_path):
    api = FakeApi()
    with pytest.raises(sb.Refused, match="not the entry session"):
        bot(tmp_path, api).enter(EXPIRY, datetime(2026, 11, 9, 10, 15), set())
    out = bot(tmp_path, api).enter(EXPIRY, NOW, set(), dry_run=True)
    assert out["status"] == "dry_run" and not api.orders


def test_a_crossed_or_empty_quote_is_refused():
    with pytest.raises(sb.Refused):
        sb.limit_prices({"bid": 0}, {"ask": 5})
    with pytest.raises(sb.Refused):
        sb.limit_prices({"bid": 4}, {"ask": 5})


def test_check_alerts_when_the_hedge_is_missing(tmp_path):
    api, notes = FakeApi(), []
    b = bot(tmp_path, api, notes)
    b.enter(EXPIRY, NOW, set())
    notes.clear()
    api.positions = {"NIFTY10NOV2625000CE": -65, "NIFTY10NOV2625100CE": 65}
    assert b.check()["status"] == "ok" and not notes
    api.positions = {"NIFTY10NOV2625000CE": -65}
    assert b.check()["status"] == "mismatch" and "ALERT" in notes[0]


def test_exit_buys_back_the_call_first_then_sells_the_hedge_and_compares_with_the_ledger(tmp_path):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter(EXPIRY, NOW, set())
    api.orders.clear()
    with pytest.raises(sb.Refused, match="runs to the 2026-11-10"):
        b.exit(today=date(2026, 11, 9))
    assert not api.orders
    done = b.exit(today=EXPIRY)
    closing = list(api.orders.values())
    assert [(o["action"], o["pricetype"]) for o in closing] == [
        ("BUY", "MARKET"),
        ("SELL", "MARKET"),
    ]
    assert closing[0]["symbol"].endswith("25000CE") and done["status"] == "closed"
    row = sb.compare(done, {"credit": 14.5, "exit_value": 1.0})
    assert row["entry_shortfall"] == pytest.approx(0.5)
    assert "exit_shortfall" in row
    with pytest.raises(sb.Refused):
        b.exit()  # nothing left open? status closed is not open


def test_the_entry_session_for_the_holiday_shifted_9_november_expiry_is_thursday_the_5th():
    """10 November 2026 is a market holiday; Sunday 8 November is a special evening session only."""
    assert sb.entry_day(date(2026, 11, 9), {date(2026, 11, 10)}) == date(2026, 11, 5)


def test_a_switch_to_live_between_the_hedge_and_the_call_stops_the_call_and_keeps_the_hedge_on_record(
    tmp_path,
):
    api, notes = (
        FakeApi(flip_after_orders=1),
        [],
    )  # Live is switched on right after the hedge is placed
    b = bot(tmp_path, api, notes)
    with pytest.raises(sb.Refused, match="never trades live"):
        b.enter(EXPIRY, NOW, set())
    assert [o["action"] for o in api.orders.values()] == ["BUY"]  # no short call was sent
    assert b.state()["status"] == "orphan_hedge" and "close it with the exit command" in notes[-1]
    with pytest.raises(sb.Refused, match="already recorded"):
        api.analyze = True
        b.enter(EXPIRY, NOW, set())  # and a second hedge is not bought


def test_a_switch_to_live_during_the_exit_leaves_the_state_saying_the_call_is_already_closed(
    tmp_path,
):
    api = FakeApi()
    b = bot(tmp_path, api)
    b.enter(EXPIRY, NOW, set())
    api.orders.clear()
    api.flip_after_orders = 1  # Live is switched on right after the call is bought back
    with pytest.raises(sb.Refused, match="never trades live"):
        b.exit(today=EXPIRY)
    assert [o["action"] for o in api.orders.values()] == ["BUY"]
    assert b.state()["status"] == "short_bought_back"
    api.analyze, api.flip_after_orders = True, None
    api.orders.clear()
    done = b.exit(today=EXPIRY)  # the retry sells the hedge and never buys the call back twice
    assert [o["action"] for o in api.orders.values()] == ["SELL"] and done["status"] == "closed"


def test_an_unfilled_buyback_is_cancelled_and_the_state_stays_open(tmp_path):
    api, notes = FakeApi(), []
    b = bot(tmp_path, api, notes)
    b.enter(EXPIRY, NOW, set())
    api.fill_buyback = False
    out = b.exit(today=EXPIRY)
    assert out["status"] == "exit_failed" and b.state()["status"] == "open"
    assert api.cancelled and "could not buy back" in notes[-1]


def test_the_saved_state_is_written_in_one_step(tmp_path):
    b = bot(tmp_path, FakeApi())
    b.save({"status": "open"})
    assert b.state() == {"status": "open"}
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]  # no temp file left behind


def test_an_order_that_fills_between_the_last_look_and_the_cancel_is_recorded_not_forgotten(
    tmp_path,
):
    api, notes = FakeApi(fill_short=False, fill_after_cancel=True), []
    state = bot(tmp_path, api, notes).enter(EXPIRY, NOW, set())
    assert state["status"] == "open" and state["short_fill"]["price"] > 0  # the call is on record
    assert "opened" in notes[-1]


def test_check_expects_no_sold_call_after_the_exit_started_and_flags_a_naked_one(tmp_path):
    api, notes = FakeApi(), []
    b = bot(tmp_path, api, notes)
    b.save(
        {
            "status": "short_bought_back",
            "sold": "NIFTY10NOV2625000CE",
            "long": "NIFTY10NOV2625100CE",
            "quantity": 65,
        }
    )
    api.positions = {"NIFTY10NOV2625100CE": 65}
    assert b.check()["status"] == "ok"  # the call is closed, the hedge is held: as recorded
    api.positions = {"NIFTY10NOV2625000CE": -65}  # a short call with no hedge
    assert b.check()["status"] == "mismatch" and "ALERT" in notes[-1]
