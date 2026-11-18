"""The ATM 200 live executor on a fake broker: entry refusals in order, exits, lost replies and imports.

Every test uses a fake client and tmp_path. Nothing reads .env, nothing calls the app, nothing writes a
real approval file. Each test sends zero orders unless it is about an entry or an exit.
"""

import ast
import csv
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import httpx
import pytest

from services.algos import live_executor_atm200 as live
from services.algos import nse_lots
from services.algos import sandbox_bot as sb
from services.algos import sandbox_bot_atm200 as sbx

MODULE_PATH = Path(__file__).resolve().parents[1] / "services" / "algos" / "live_executor_atm200.py"
ENTRY_DAY = date(2026, 11, 9)  # a Monday
NEXT_DAY = date(2026, 11, 10)
EXPIRY = date(2026, 11, 12)
NOW = datetime(2026, 11, 9, 10, 16)
SOLD = sb.contract_symbol(EXPIRY, 25000)
LONG = sb.contract_symbol(EXPIRY, 25200)
FRESH_VIX = (date(2026, 11, 6), 14.0)
QTY = nse_lots.nifty_lot(EXPIRY)  # one lot; checked against the lot the shared code picks below
NO_HOLIDAYS: set[date] = set()
CALM = {SOLD: 20.0, LONG: 6.0}
FOLLOW_UP = datetime(2026, 11, 9, 10, 20)
ENTRY_SESSION_1100 = datetime(2026, 11, 9, 11, 0)
ORDER_KEYS = {
    "strategy",
    "exchange",
    "symbol",
    "action",
    "quantity",
    "pricetype",
    "product",
    "price",
    "live_only",
}
ALLOWED_MODULES = {
    "services.algos.atm200_rule",
    "services.algos.sandbox_bot",
    "services.algos.sandbox_bot_atm200",
    "services.algos.nse_lots",
    "services.algos.sandbox_round_trips",
    "utils.logging",
}
FORBIDDEN_NAMES = ("requests", "httpx", "urllib", "aiohttp", "socket", "subprocess", "broker")


@pytest.fixture(autouse=True)
def india_clock(monkeypatch):
    """Every test runs on an India clock; the clock test replaces it with a wrong offset."""
    monkeypatch.setattr(sbx, "machine_utc_offset", lambda: sbx.INDIA_OFFSET)


class LiveBroker:
    """Fake OpenAlgo with a broker book. A sent order fills at once unless its (action, symbol) is pending.

    A live order is refused while the analyzer is on, as the order service does. Any Sandbox marker on
    an order is a test failure, not a refusal: the live executor must never send one.
    """

    def __init__(self, pending=()):
        self.analyze = False
        self.ltp = dict(CALM)
        self.quotes = {SOLD: (19.5, 20.5), LONG: (5.5, 6.0)}
        self.pending, self.crash = set(pending), None
        self.orders, self.calls = {}, []
        self.flip_after_orders = None
        self.spots = []  # Nifty prices returned in turn; the default is 25010 once they run out
        self.spot_quotes = 0

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

    def post(self, path, **p):
        self.calls.append((path, p))
        if path == "/api/v1/analyzer":
            return {"status": "success", "data": {"analyze_mode": self.analyze}}
        if path == "/api/v1/quotes":
            if p["symbol"] == sb.UNDERLYING:
                self.spot_quotes += 1
                return {"data": {"ltp": self.spots.pop(0) if self.spots else 25010.0}}
            bid, ask = self.quotes[p["symbol"]]
            return {"data": {"ltp": self.ltp[p["symbol"]], "bid": bid, "ask": ask}}
        if path == "/api/v1/placeorder":
            assert "sandbox_only" not in p, "a live executor must never send sandbox_only"
            assert p.get("live_only") is True, "every live order carries live_only"
            if self.analyze:
                return {"status": "error", "message": "analyzer mode is on"}
            oid = f"id{len(self.orders) + 1}"
            status = "open" if (p["action"], p["symbol"]) in self.pending else "complete"
            price = p["price"] or self.ltp[p["symbol"]]
            self.orders[oid] = {"p": p, "status": status, "price": price, "stamp": sbx.now_ist()}
            self._maybe_crash("sent", p["action"], p["symbol"])
            if self.flip_after_orders == len(self.orders):
                self.analyze = True  # analyzer is switched on right after this order
            return {"status": "success", "orderid": oid}
        if path == "/api/v1/orderstatus":
            order = self.orders[p["orderid"]]
            self._maybe_crash("poll", order["p"]["action"], order["p"]["symbol"])
            return self._status_reply(order)
        if path == "/api/v1/orderbook":
            rows = []
            for oid, order in self.orders.items():
                rows.append(
                    {
                        "orderid": oid,
                        "symbol": order["p"]["symbol"],
                        "action": order["p"]["action"],
                        "quantity": order["p"]["quantity"],
                        "strategy": order["p"]["strategy"],
                        "timestamp": order["stamp"].strftime("%Y-%m-%d %H:%M:%S"),
                        **self._status_reply(order)["data"],
                    }
                )
            return {"status": "success", "data": {"orders": rows}}
        if path == "/api/v1/cancelorder":
            order = self.orders[p["orderid"]]
            if order["status"] == "open":
                order["status"] = "cancelled"
            return {"status": "success"}
        if path == "/api/v1/openposition":
            label_held = self.held(p["symbol"]) if p["strategy"] == live.LIVE_STRATEGY else 0
            return {"status": "success", "quantity": str(label_held)}
        raise AssertionError(path)

    @staticmethod
    def _status_reply(order):
        filled = order["p"]["quantity"] if order["status"] == "complete" else 0
        return {
            "status": "success",
            "data": {
                "order_status": order["status"],
                "average_price": order["price"],
                "quantity": order["p"]["quantity"],
                "filled_quantity": filled,
            },
        }


def placed(api):
    return [p for path, p in api.calls if path == "/api/v1/placeorder"]


def order_sequence(api):
    return [(o["action"], o["symbol"]) for o in placed(api)]


def assert_flat(api):
    assert api.held(SOLD) == 0 and api.held(LONG) == 0


def naked_short(api):
    return api.held(SOLD) < 0 and api.held(LONG) < -api.held(SOLD)


def no_repeats(api):
    sent = order_sequence(api)
    return len(sent) == len(set(sent))


def paths(root):
    base = root / "db" / "live_executor_atm200"
    return base / "state.json", base / "trades.csv", base / "approval.json"


def write_approval(root, **changes):
    _, _, approval = paths(root)
    approval.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "date": "2026-11-09",
        "strategy": "ATM200-live",
        "max_lots": 1,
        "approved_by": "owner",
        "written_at": "2026-11-09T09:00:00",
        "expires_at": "2026-11-09T15:30:00",
        "gate_waiver": {"waived": False, "owner_sentence": ""},
        "pause_cleared_on": None,
    }
    body.update(changes)
    approval.write_text(json.dumps(body), encoding="utf-8")
    return approval


def make_bot(
    root,
    api,
    notes,
    *,
    gate=False,
    margin=30000,
    funds=100000,
    positions=lambda: [],
    margin_fn=None,
):
    state, trades, approval = paths(root)
    return live.LiveATM200Bot(
        api,
        state,
        trades,
        approval,
        margin_required=margin_fn or (lambda sold, long, qty: margin),
        funds_available=lambda: funds,
        positions=positions,
        live_gate_on=gate,
        notify=notes.append,
        wait=10,
    )


def write_pilot_loss(root, gross=-15000):
    _, trades, _ = paths(root)
    trades.parent.mkdir(parents=True, exist_ok=True)
    with trades.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sbx.TRADE_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "entry_date": "2026-11-02",
                "sold": "NIFTY05NOV26 25000CE",
                "quantity": QTY,
                "gross_rupees": gross,
                "exit_session": "2026-11-03",
                "exit_time": "2026-11-03 15:00",
                "exit_reason": "time",
            }
        )


def open_spread(root, api, notes):
    """Enters once with a valid approval; afterwards the price moves so an exit is due."""
    write_approval(root)
    b = make_bot(root, api, notes)
    b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)
    api.ltp = {SOLD: 5.0, LONG: 4.0}  # spread value 1.0 is at or below the target
    return b


def assert_one_live_alert(notes, needle):
    matching = [n for n in notes if needle in n]
    assert matching, notes
    assert all(n.startswith("LIVE:") for n in notes), notes


def refused_without_orders(root, api, notes, **bot_kwargs):
    b = make_bot(root, api, notes, **bot_kwargs)
    with pytest.raises(sb.Refused) as info:
        b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)
    assert not placed(api)
    assert all(n.startswith("LIVE:") for n in notes), notes
    assert len(notes) >= 1
    return b, str(info.value)


# 1 ---- refusals, in the order the spec gives -------------------------------------------------
def test_refusal_1_analyzer_on_refuses_before_anything_else(tmp_path):
    api, notes = LiveBroker(), []
    api.analyze = True
    write_approval(tmp_path)
    _, why = refused_without_orders(tmp_path, api, notes)
    assert "Analyzer mode is on" in why
    assert_one_live_alert(notes, "Analyzer mode is on")


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(hours=4)])
def test_refusal_2_a_machine_not_on_india_time_refuses(tmp_path, monkeypatch, offset):
    monkeypatch.setattr(sbx, "machine_utc_offset", lambda: offset)
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    _, why = refused_without_orders(tmp_path, api, notes)
    assert "not on India time" in why
    assert_one_live_alert(notes, "India time")


@pytest.mark.parametrize("when", [datetime(2026, 11, 9, 10, 14), datetime(2026, 11, 9, 10, 20)])
def test_refusal_2_outside_1015_to_1020_refuses(tmp_path, when):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    b = make_bot(tmp_path, api, notes)
    with pytest.raises(sb.Refused, match="10:15 to 10:20"):
        b.enter_spread(EXPIRY, when, NO_HOLIDAYS, FRESH_VIX)
    assert not placed(api) and notes and notes[0].startswith("LIVE:")


def test_refusal_2_a_weekend_refuses(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path, date="2026-11-14")
    b = make_bot(tmp_path, api, notes)
    with pytest.raises(sb.Refused, match="not a trading day"):
        b.enter_spread(EXPIRY, datetime(2026, 11, 14, 10, 16), NO_HOLIDAYS, FRESH_VIX)
    assert not placed(api)


def test_refusal_3_no_approval_file_refuses(tmp_path):
    api, notes = LiveBroker(), []
    _, why = refused_without_orders(tmp_path, api, notes)
    assert "No owner approval" in why


@pytest.mark.parametrize(
    "changes, phrase",
    [
        ({"date": "2026-11-08"}, "dated another day"),
        ({"expires_at": "2026-11-09T10:10:00"}, "expired"),
        ({"expires_at": "not a time"}, "no valid expiry"),
        ({"strategy": "ATM200-sandbox"}, "another strategy"),
        ({"max_lots": 2}, "other than one"),
        ({"approved_by": ""}, "no approver"),
    ],
)
def test_refusal_3_an_approval_that_does_not_match_today_refuses(tmp_path, changes, phrase):
    api, notes = LiveBroker(), []
    write_approval(tmp_path, **changes)
    _, why = refused_without_orders(tmp_path, api, notes)
    assert phrase in why


def test_refusal_4_gate_on_without_a_waiver_refuses(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    _, why = refused_without_orders(tmp_path, api, notes, gate=True)
    assert "Live gate is on" in why


def test_refusal_4_gate_on_with_an_empty_sentence_refuses(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path, gate_waiver={"waived": True, "owner_sentence": "   "})
    _, why = refused_without_orders(tmp_path, api, notes, gate=True)
    assert "Live gate is on" in why


def test_refusal_5_cash_below_margin_plus_premium_plus_buffer_refuses(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    # need = 30,000 margin + 6.0 x 65 premium + 3,000 buffer (the minimum) = 33,390; cash 32,000 is 1,390 short
    _, why = refused_without_orders(tmp_path, api, notes, margin=30000, funds=32000)
    assert "Rs 33,390 needed" in why and "Rs 1,390 short" in why


def test_refusal_5_the_trade_is_not_shrunk_to_fit_the_cash(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    refused_without_orders(tmp_path, api, notes, margin=30000, funds=32000)
    assert not placed(api)


def test_the_buffer_is_the_larger_of_three_thousand_or_ten_percent_of_the_margin():
    assert live.margin_buffer(20000) == 3000
    assert live.margin_buffer(45770) == pytest.approx(4577)
    assert live.MARGIN_BUFFER_MIN == 3000 and live.MARGIN_BUFFER_SHARE == 0.10


def test_cash_short_of_margin_premium_and_buffer_refuses_with_the_shortfall(tmp_path):
    api, notes = LiveBroker(), []
    api.ltp[LONG] = 4127 / QTY  # bought call premium of Rs 4,127 for one lot
    write_approval(tmp_path)
    premium = api.ltp[LONG] * QTY
    need = 45770.0 + premium + live.margin_buffer(45770.0)
    _, why = refused_without_orders(tmp_path, api, notes, margin=45770, funds=32041)
    assert f"Cash of Rs 32,041 is Rs {need - 32041:,.0f} short of the Rs {need:,.0f} needed" in why
    assert "margin Rs 45,770" in why and "bought call premium Rs 4,127" in why
    assert "buffer Rs 4,577" in why
    assert not placed(api)


def test_cash_exactly_equal_to_the_need_passes(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)  # premium stays at the calm 6.0 so the spread still passes its rule
    need = 45770.0 + CALM[LONG] * QTY + live.margin_buffer(45770.0)
    b = make_bot(tmp_path, api, notes, margin=45770, funds=need)
    assert b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)["status"] == "open"
    assert order_sequence(api) == [("BUY", LONG), ("SELL", SOLD)]


def test_refusal_6_a_nifty_option_held_under_another_label_refuses(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    held = [{"symbol": SOLD, "quantity": -QTY, "strategy": "S3n-sandbox"}]
    _, why = refused_without_orders(tmp_path, api, notes, positions=lambda: held)
    assert "already has a position" in why and SOLD in why


def test_refusal_6_unreadable_positions_refuse(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)

    def broken():
        raise RuntimeError("the book did not answer")

    _, why = refused_without_orders(tmp_path, api, notes, positions=broken)
    assert "could not be read" in why


def test_refusal_7_a_quantity_other_than_one_lot_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "lot_quantity", lambda on: 2 * QTY)
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    _, why = refused_without_orders(tmp_path, api, notes)
    assert "exactly one Nifty lot" in why


def test_refusal_8_a_pilot_loss_at_the_pause_line_pauses_entries(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    write_pilot_loss(tmp_path, gross=-10000)  # net after charges is below -10,000
    b, why = refused_without_orders(tmp_path, api, notes)
    assert "paused" in why
    assert b.state()["status"] == "paused"


def test_refusal_8_the_pause_is_cleared_only_by_pause_cleared_on_today(tmp_path):
    api, notes = LiveBroker(), []
    write_pilot_loss(tmp_path)
    write_approval(tmp_path, pause_cleared_on="2026-11-08")  # yesterday does not clear it
    refused_without_orders(tmp_path, api, notes)
    assert not placed(api)

    write_approval(tmp_path, pause_cleared_on="2026-11-09")
    b = make_bot(tmp_path, api, [])
    assert b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)["status"] == "open"


def test_the_first_refusal_in_order_is_the_one_reported(tmp_path):
    api, notes = LiveBroker(), []
    api.analyze = True  # refusal 1
    _, why = refused_without_orders(tmp_path, api, notes)  # no approval as well: refusal 3
    assert "Analyzer mode is on" in why


def test_a_gate_waiver_enters_and_sends_the_waiver_alert(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(
        tmp_path, gate_waiver={"waived": True, "owner_sentence": "I accept the first live pilot."}
    )
    b = make_bot(tmp_path, api, notes, gate=True)
    assert b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)["status"] == "open"
    assert "LIVE: ATM 200 Live gate bypassed by owner waiver" in notes
    assert order_sequence(api) == [("BUY", LONG), ("SELL", SOLD)]


# payload and the live label -----------------------------------------------------------------------
def test_every_entry_order_matches_the_live_payload(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    make_bot(tmp_path, api, notes).enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)
    orders = placed(api)
    assert [(o["action"], o["symbol"]) for o in orders] == [("BUY", LONG), ("SELL", SOLD)]
    for p in orders:
        assert set(p) == ORDER_KEYS
        assert "sandbox_only" not in p
        assert p["live_only"] is True
        assert p["strategy"] == "ATM200-live"
        assert p["product"] == "NRML"
        assert p["exchange"] == "NFO"
        assert p["quantity"] == QTY == sb.lot_quantity(NOW)


def test_the_approval_file_is_read_and_never_written(tmp_path):
    api, notes = LiveBroker(), []
    approval = write_approval(tmp_path)
    before = approval.read_bytes()
    make_bot(tmp_path, api, notes).enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)
    api.ltp = {SOLD: 5.0, LONG: 4.0}
    make_bot(tmp_path, api, notes).check_spread(ENTRY_SESSION_1100, NO_HOLIDAYS)
    assert len(placed(api)) == 4  # the entry and the exit were both sent
    assert approval.read_bytes() == before


# analyzer switched on between orders ---------------------------------------------------------------
def test_analyzer_switched_on_between_orders_stops_and_alerts_once(tmp_path):
    api, notes = LiveBroker(), []
    api.flip_after_orders = 1  # analyzer comes on right after the hedge is booked
    write_approval(tmp_path)
    b = make_bot(tmp_path, api, notes)
    with pytest.raises(sb.Refused, match="Analyzer mode is on"):
        b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)
    assert order_sequence(api) == [("BUY", LONG)]  # the short sell was never sent
    assert b.state()["status"] == "orphan_hedge" and "Analyzer" in b.state()["needs_attention"]
    assert len([n for n in notes if "ALERT" in n]) == 1
    assert all(n.startswith("LIVE:") for n in notes)


def test_exits_are_refused_while_the_analyzer_is_on_and_alert(tmp_path):
    api, notes = LiveBroker(), []
    open_spread(tmp_path, api, notes)
    api.analyze = True
    sent = len(placed(api))
    with pytest.raises(sb.Refused, match="Analyzer mode is on"):
        make_bot(tmp_path, api, notes).check_spread(ENTRY_SESSION_1100, NO_HOLIDAYS)
    assert len(placed(api)) == sent
    assert notes[-1].startswith("LIVE:")


# exits and flatten are never blocked by approval, pause or gate ------------------------------------
def test_an_expired_or_missing_approval_still_allows_the_exit_and_a_flatten(tmp_path):
    api, notes = LiveBroker(), []
    open_spread(tmp_path, api, notes)
    _, _, approval = paths(tmp_path)
    approval.unlink()  # no approval at all: entries are refused, exits are not
    write_pilot_loss(tmp_path)  # and the pilot is paused
    b = make_bot(tmp_path, api, notes, gate=True)
    done = b.check_spread(ENTRY_SESSION_1100, NO_HOLIDAYS)
    assert done["status"] == "closed" and done["exit_reason"] == "target"
    assert_flat(api)


def test_an_expired_approval_still_allows_a_flatten(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    make_bot(tmp_path, api, notes).enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)
    write_approval(tmp_path, expires_at="2026-11-09T10:10:00")  # now expired
    sent = len(placed(api))
    done = make_bot(tmp_path, api, notes, gate=True).flatten(yes=True)
    assert done["status"] == "flattened_by_person"
    assert len(placed(api)) == sent + 2
    assert_flat(api)


def test_the_exit_runs_on_its_own_when_the_approval_has_expired(tmp_path):
    api, notes = LiveBroker(), []
    open_spread(tmp_path, api, notes)
    write_approval(tmp_path, expires_at="2026-11-09T10:10:00")
    done = make_bot(tmp_path, api, notes).check_spread(ENTRY_SESSION_1100, NO_HOLIDAYS)
    assert done["status"] == "closed" and done["exit_reason"] == "target"
    assert order_sequence(api)[-2:] == [("BUY", SOLD), ("SELL", LONG)]
    assert_flat(api)


def test_every_alert_of_a_full_cycle_starts_with_live(tmp_path):
    api, notes = LiveBroker(), []
    open_spread(tmp_path, api, notes)
    api.ltp = {SOLD: 5.0, LONG: 4.0}
    make_bot(tmp_path, api, notes).check_spread(ENTRY_SESSION_1100, NO_HOLIDAYS)
    assert notes and all(n.startswith("LIVE:") for n in notes)
    assert_flat(api)


# lost replies and kills: the same cases as the Sandbox executor -----------------------------------
FAILURES = ["timeout", "interrupt"]
ENTRY_POINTS = {
    "hedge_sent": ("sent", "BUY", LONG),
    "hedge_fill_awaited": ("poll", "BUY", LONG),
    "short_sent": ("sent", "SELL", SOLD),
    "short_fill_awaited": ("poll", "SELL", SOLD),
}
EXIT_POINTS = {
    "buyback_sent": ("sent", "BUY", SOLD),
    "sellhedge_sent": ("sent", "SELL", LONG),
}


def failure(kind):
    if kind == "timeout":
        return httpx.TimeoutException("the broker did not answer")
    return KeyboardInterrupt()


@pytest.mark.parametrize("kind", FAILURES)
@pytest.mark.parametrize("point", list(ENTRY_POINTS))
def test_a_lost_or_killed_entry_order_leaves_a_state_that_needs_a_person(tmp_path, point, kind):
    api, notes = LiveBroker(), []
    when, action, symbol = ENTRY_POINTS[point]
    api.arm(when, action, symbol, failure(kind))
    write_approval(tmp_path)
    b = make_bot(tmp_path, api, notes)
    with pytest.raises(type(failure(kind))):
        b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)
    sent_before = len(placed(api))
    notes.clear()  # the bot keeps the list it was built with, so its alerts still go through the live label
    out = b.check_spread(FOLLOW_UP, NO_HOLIDAYS)
    assert out["status"] == "needs_attention"
    assert len(notes) == 1 and "ALERT" in notes[0] and notes[0].startswith("LIVE:")
    assert len(placed(api)) == sent_before
    assert no_repeats(api) and not naked_short(api)


@pytest.mark.parametrize("kind", FAILURES)
@pytest.mark.parametrize("point", list(EXIT_POINTS))
def test_a_lost_or_killed_exit_order_leaves_a_safe_state_and_no_new_order(tmp_path, point, kind):
    api, notes = LiveBroker(), []
    b = open_spread(tmp_path, api, notes)
    when, action, symbol = EXIT_POINTS[point]
    api.arm(when, action, symbol, failure(kind))
    with pytest.raises(type(failure(kind))):
        b.check_spread(ENTRY_SESSION_1100, NO_HOLIDAYS)
    sent_before = len(placed(api))
    notes.clear()
    out = b.check_spread(ENTRY_SESSION_1100, NO_HOLIDAYS)
    assert out["status"] == "mismatch"
    assert len(notes) == 1 and "ALERT" in notes[0]
    assert len(placed(api)) == sent_before
    assert no_repeats(api) and not naked_short(api)


@pytest.mark.parametrize("point", list(EXIT_POINTS))
def test_an_exit_order_still_working_is_not_sent_again(tmp_path, point):
    when, action, symbol = EXIT_POINTS[point]
    api, notes = LiveBroker(pending={(action, symbol)}), []
    b = open_spread(tmp_path, api, notes)
    api.arm(when, action, symbol, httpx.TimeoutException("the broker did not answer"))
    with pytest.raises(httpx.TimeoutException):
        b.check_spread(ENTRY_SESSION_1100, NO_HOLIDAYS)
    b.check_spread(ENTRY_SESSION_1100, NO_HOLIDAYS)
    assert no_repeats(api)


def test_a_lost_hedge_reply_then_flatten_sells_only_the_hedge(tmp_path):
    api, notes = LiveBroker(), []
    api.arm("sent", "BUY", LONG, httpx.TimeoutException("the broker did not answer"))
    write_approval(tmp_path)
    b = make_bot(tmp_path, api, notes)
    with pytest.raises(httpx.TimeoutException):
        b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)
    sent = len(placed(api))
    b.flatten(yes=True)
    assert [(o["action"], o["symbol"]) for o in placed(api)[sent:]] == [("SELL", LONG)]
    assert b.state()["status"] == sbx.FLATTENED


def test_flatten_refuses_without_yes_and_in_analyzer_mode(tmp_path):
    api, notes = LiveBroker(), []
    b = open_spread(tmp_path, api, notes)
    sent = len(placed(api))
    with pytest.raises(sb.Refused, match="--yes"):
        b.flatten(yes=False)
    api.analyze = True
    with pytest.raises(sb.Refused, match="Analyzer mode is on"):
        b.flatten(yes=True)
    assert len(placed(api)) == sent


def test_a_flatten_closes_a_live_spread_and_books_nothing(tmp_path):
    api, notes = LiveBroker(), []
    b = open_spread(tmp_path, api, notes)
    b.flatten(yes=True)
    assert order_sequence(api)[-2:] == [("BUY", SOLD), ("SELL", LONG)]
    assert_flat(api)
    assert b.state()["status"] == sbx.FLATTENED
    _, trades, _ = paths(tmp_path)
    assert not trades.exists()


# margin, strikes and the one quote -----------------------------------------------------------------
def test_the_margin_check_and_the_entry_name_the_same_two_contracts(tmp_path):
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    seen = []

    def record(sold, long, qty):
        seen.append((sold, long, qty))
        return 30000

    b = make_bot(tmp_path, api, notes, margin_fn=record)
    assert b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)["status"] == "open"
    assert seen == [(SOLD, LONG, QTY)]
    assert [(p["symbol"], p["quantity"]) for p in placed(api)] == [(LONG, QTY), (SOLD, QTY)]


def test_a_spot_move_between_the_two_quotes_cannot_change_the_strikes(tmp_path):
    api, notes = LiveBroker(), []
    api.spots = [25010.0, 25400.0, 25400.0]  # a second Nifty quote would pick the 25400 strikes
    write_approval(tmp_path)
    seen = []

    def record(sold, long, qty):
        seen.append((sold, long, qty))
        return 30000

    b = make_bot(tmp_path, api, notes, margin_fn=record)
    assert b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)["status"] == "open"
    assert api.spot_quotes == 1
    assert seen == [(SOLD, LONG, QTY)]
    assert order_sequence(api) == [("BUY", LONG), ("SELL", SOLD)]


# structural cap and one position -----------------------------------------------------------------
@pytest.mark.parametrize(
    "lot, lots, opens",
    [(200, 1, False), (65, 1, True), (65, 2, True), (65, 3, False)],
)
def test_the_structural_cap_refuses_a_largest_loss_above_the_daily_cap(
    tmp_path, monkeypatch, lot, lots, opens
):
    # Largest loss = width x lot x lots: 200 x 65 x 1 = 13,000 passes; 200 x 200 x 1 and 200 x 65 x 3 do not.
    monkeypatch.setattr(nse_lots, "nifty_lot", lambda expiry: lot)
    monkeypatch.setattr(sb, "lot_quantity", lambda on: lot * lots)
    monkeypatch.setattr(live, "MAX_LOTS", lots)
    api, notes = LiveBroker(), []
    write_approval(tmp_path, max_lots=lots)
    b = make_bot(tmp_path, api, notes, funds=10**9, margin=0)
    if opens:
        assert b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)["status"] == "open"
        return
    with pytest.raises(sb.Refused, match="daily cap"):
        b.enter_spread(EXPIRY, NOW, NO_HOLIDAYS, FRESH_VIX)
    assert not placed(api)
    assert_one_live_alert(notes, "daily cap")


def test_the_pilot_limits_and_the_cap_the_real_lot_fits():
    # One lot of 65 at a 200-point width is 13,000 of largest loss, under the 27,000 cap.
    assert live.DAILY_CAP == 27000 and live.MAX_LOTS == 1
    assert sbx.rule.WIDTH * 65 * live.MAX_LOTS <= live.DAILY_CAP
    # No position counter is kept: the Nifty-option refusal is the one-position rule.
    assert not hasattr(live, "MAX_POSITIONS")


def test_a_second_spread_cannot_open_while_any_nifty_option_is_held(tmp_path):
    # The one-position rule is the Nifty-option refusal: a different strike is refused too.
    api, notes = LiveBroker(), []
    write_approval(tmp_path)
    other = sb.contract_symbol(EXPIRY, 25100)
    held = [{"symbol": other, "quantity": -QTY, "strategy": "ATM200-live"}]
    _, why = refused_without_orders(tmp_path, api, notes, positions=lambda: held)
    assert "already has a position" in why and other in why


# import isolation and no runner --------------------------------------------------------------------
def import_violations(source: str) -> list[str]:
    """Imports outside the allowed list, and identifiers that name a network, process or broker module."""
    tree = ast.parse(source)
    stdlib = sys.stdlib_module_names
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(part in FORBIDDEN_NAMES for part in alias.name.split(".")):
                    bad.append(alias.name)
                elif alias.name.split(".")[0] not in stdlib and alias.name not in ALLOWED_MODULES:
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                bad.append("relative import")
                continue
            module = node.module or ""
            if any(part in FORBIDDEN_NAMES for part in module.split(".")):
                bad.append(module)
                continue
            if module.split(".")[0] in stdlib:
                continue
            if module == "services.algos":
                for alias in node.names:
                    if f"{module}.{alias.name}" not in ALLOWED_MODULES:
                        bad.append(f"{module}.{alias.name}")
            elif module not in ALLOWED_MODULES:
                bad.append(module)
        names = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        for name in names:
            if any(token in name.lower() for token in FORBIDDEN_NAMES):
                bad.append(name)
    return bad


def test_the_module_imports_only_the_allowed_modules_and_the_standard_library():
    assert import_violations(MODULE_PATH.read_text(encoding="utf-8")) == []


def test_the_import_check_catches_a_forbidden_import_and_name():
    assert import_violations("import requests\n")
    assert import_violations("import urllib.request\n")
    assert import_violations("from broker.upstox import api\n")
    assert import_violations("from services.algos import place_order\n")
    assert import_violations("import subprocess\n")
    assert import_violations("client = httpx_client()\n")
    assert import_violations("import json\nfrom services.algos import nse_lots\n") == []


def test_the_executor_logs_through_utils_logging_only():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            imported.add(node.module or "")
    utils_imports = {name for name in imported if name.split(".")[0] == "utils"}
    assert utils_imports == {"utils.logging"}
    assert "logging" not in imported
    assert "logger = get_logger(__name__)" in source


def test_the_module_has_no_runner_entry_point():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "__main__" not in source
    assert "if __name__" not in source
