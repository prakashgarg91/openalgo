"""Whole-cycle runs of the ATM 200 sandbox bot on a fake broker, driven the way the schedule drives it.

Each scenario runs the calls in order: an entry at 10:16, then a check every five minutes from 10:20
to 15:00 across two sessions, with a fresh bot object where a restart is the point. The fake client
keeps a broker book (every order fills at once), so the tests see the order sequence, the trade file
and the final book. No network, no clock, no database: the state and trade files live in tmp_path.
"""

import csv
from datetime import date, datetime, time, timedelta

import httpx
import pytest

from services.algos import atm200_rule as rule
from services.algos import sandbox_bot as sb
from services.algos import sandbox_bot_atm200 as atm

ENTRY_DAY = date(2026, 11, 9)  # a Monday
NEXT_DAY = date(2026, 11, 10)  # the session after entry: the exit session
THIRD_DAY = date(2026, 11, 11)
EXPIRY = date(2026, 11, 12)
ENTRY_AT = datetime(2026, 11, 9, 10, 16)
SOLD = sb.contract_symbol(EXPIRY, 25000)
LONG = sb.contract_symbol(EXPIRY, 25200)
FRESH_VIX = (date(2026, 11, 6), 14.0)
QTY = sb.lot_quantity(ENTRY_AT)
NO_HOLIDAYS: set[date] = set()
ENTRY_ORDERS = [("BUY", LONG), ("SELL", SOLD)]  # the hedge goes first
EXIT_ORDERS = [("BUY", SOLD), ("SELL", LONG)]  # the buy-back goes first
CALM = {SOLD: 20.0, LONG: 6.0}  # credit 14.0 at the last price, value 14.0: held
TARGET_PRICES = {SOLD: 5.0, LONG: 4.0}  # value 1.0, at or under the 31 percent target
STOP_PRICES = {SOLD: 40.0, LONG: 4.0}  # value 36.0, at or over the 250 percent stop


def ticks(day, first=(10, 20), last=(15, 0)):
    """The 5-minute check times of one session, from the first to the last inclusive."""
    moment, end = datetime.combine(day, time(*first)), datetime.combine(day, time(*last))
    out = []
    while moment <= end:
        out.append(moment)
        moment += timedelta(minutes=5)
    return out


class Broker:
    """Fake OpenAlgo with a broker book. Every order fills at once: a limit at its price, a market at the last price."""

    def __init__(self):
        self.analyze = True
        self.ltp = dict(CALM)
        self.quotes = {SOLD: (19.5, 20.5), LONG: (5.5, 6.0)}
        self.orders, self.calls = {}, []
        self.down = False

    def held(self, symbol):
        total = 0
        for order in self.orders.values():
            p = order["p"]
            if p["symbol"] == symbol:
                total += p["quantity"] if p["action"] == "BUY" else -p["quantity"]
        return total

    def post(self, path, **p):
        if self.down:
            raise httpx.ConnectError("the app did not answer")
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
            price = p["price"] or self.ltp[p["symbol"]]
            self.orders[oid] = {"p": p, "price": price, "stamp": atm.now_ist()}
            return {"status": "success", "orderid": oid}
        if path == "/api/v1/orderstatus":
            return {"status": "success", "data": self._status(self.orders[p["orderid"]])}
        if path == "/api/v1/orderbook":
            rows = [
                {
                    "orderid": oid,
                    "symbol": o["p"]["symbol"],
                    "action": o["p"]["action"],
                    "quantity": o["p"]["quantity"],
                    "strategy": o["p"]["strategy"],
                    "timestamp": o["stamp"].strftime("%Y-%m-%d %H:%M:%S"),
                    **self._status(o),
                }
                for oid, o in self.orders.items()
            ]
            return {"status": "success", "data": {"orders": rows}}
        if path == "/api/v1/cancelorder":
            return {"status": "success"}
        if path == "/api/v1/openposition":
            label = p["strategy"]
            held = self.held(p["symbol"]) if label == atm.STRATEGY else 0
            return {"status": "success", "quantity": str(held)}
        if path == "/api/v1/positionbook":
            symbols = sorted({o["p"]["symbol"] for o in self.orders.values()})
            rows = [{"symbol": s, "quantity": self.held(s)} for s in symbols if self.held(s)]
            return {"status": "success", "data": rows}
        raise AssertionError(path)

    @staticmethod
    def _status(order):
        qty = order["p"]["quantity"]
        return {
            "order_status": "complete",
            "average_price": order["price"],
            "quantity": qty,
            "filled_quantity": qty,
        }


def placed(api):
    return [p for path, p in api.calls if path == "/api/v1/placeorder"]


def order_sequence(api):
    return [(o["action"], o["symbol"]) for o in placed(api)]


def assert_flat(api):
    assert api.held(SOLD) == 0 and api.held(LONG) == 0


def trade_rows(root):
    path = root / "db" / "trades.csv"
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def make_bot(root, api, notes):
    """A bot on the state and trade files under ``root``. A new call with the same root is a restart."""
    return atm.ATM200Bot(
        api,
        root / "db" / "state.json",
        root / "db" / "trades.csv",
        notify=notes.append,
        wait=10,
    )


def run_checks(bot, moments, stop_on_close=True):
    """Runs the checks in order and returns [(moment, result)], stopping once the trade is closed."""
    done = []
    for moment in moments:
        result = bot.check_spread(moment, NO_HOLIDAYS)
        done.append((moment, result))
        if stop_on_close and result["status"] == "closed":
            break
    return done


def test_a_clean_cycle_ends_in_a_time_exit_at_the_next_sessions_1500_check(tmp_path):
    api, notes = Broker(), []
    bot = make_bot(tmp_path, api, notes)
    entered = bot.enter_spread(EXPIRY, ENTRY_AT, NO_HOLIDAYS, FRESH_VIX)
    assert entered["status"] == "open"

    run = run_checks(bot, ticks(ENTRY_DAY) + ticks(NEXT_DAY))

    held_checks, (last_moment, last) = run[:-1], run[-1]
    assert all(result == {"status": "held", "value": 14.0} for _, result in held_checks)
    assert last_moment == datetime(2026, 11, 10, 15, 0)
    assert last["status"] == "closed" and last["exit_reason"] == "time"
    assert last["exit_note"] == ""
    assert order_sequence(api) == ENTRY_ORDERS + EXIT_ORDERS
    assert all(o["sandbox_only"] is True for o in placed(api))
    rows = trade_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["sold"] == SOLD and rows[0]["exit_reason"] == "time"
    assert rows[0]["exit_session"] == NEXT_DAY.isoformat()
    assert_flat(api)


def test_a_target_hit_on_the_entry_day_closes_the_trade_that_day(tmp_path):
    api, notes = Broker(), []
    bot = make_bot(tmp_path, api, notes)
    bot.enter_spread(EXPIRY, ENTRY_AT, NO_HOLIDAYS, FRESH_VIX)

    moments = ticks(ENTRY_DAY)
    run = []
    for moment in moments:
        if moment == datetime(2026, 11, 9, 11, 0):
            api.ltp = dict(TARGET_PRICES)
        result = bot.check_spread(moment, NO_HOLIDAYS)
        run.append((moment, result))
        if result["status"] == "closed":
            break

    moment, result = run[-1]
    assert moment == datetime(2026, 11, 9, 11, 0)
    assert result["status"] == "closed" and result["exit_reason"] == "target"
    assert result["exit_note"] == ""
    assert order_sequence(api) == ENTRY_ORDERS + EXIT_ORDERS
    rows = trade_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["exit_reason"] == "target"
    assert rows[0]["exit_time"].startswith("2026-11-09")
    assert_flat(api)


def test_a_stop_hit_closes_the_trade_and_later_checks_send_nothing(tmp_path):
    api, notes = Broker(), []
    bot = make_bot(tmp_path, api, notes)
    bot.enter_spread(EXPIRY, ENTRY_AT, NO_HOLIDAYS, FRESH_VIX)

    for moment in ticks(ENTRY_DAY):
        if moment == datetime(2026, 11, 9, 11, 0):
            api.ltp = dict(STOP_PRICES)
        if bot.check_spread(moment, NO_HOLIDAYS)["status"] == "closed":
            break
    orders_after_close = len(placed(api))
    later = [bot.check_spread(m, NO_HOLIDAYS) for m in ticks(NEXT_DAY)]

    assert later and all(result["status"] == "closed" for result in later)
    assert len(placed(api)) == orders_after_close
    assert order_sequence(api) == ENTRY_ORDERS + EXIT_ORDERS
    rows = trade_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["exit_reason"] == "stop"
    assert_flat(api)


def test_a_restart_mid_trade_continues_without_a_second_entry(tmp_path):
    api, notes = Broker(), []
    first = make_bot(tmp_path, api, notes)
    first.enter_spread(EXPIRY, ENTRY_AT, NO_HOLIDAYS, FRESH_VIX)
    assert run_checks(first, ticks(ENTRY_DAY, last=(12, 0)), stop_on_close=False)

    restarted = make_bot(tmp_path, api, notes)  # a new process reads the same state file
    assert restarted.state()["status"] == "open"
    with pytest.raises(sb.Refused, match="still recorded"):
        restarted.enter_spread(EXPIRY, datetime(2026, 11, 9, 12, 30), NO_HOLIDAYS, FRESH_VIX)
    run = run_checks(restarted, ticks(ENTRY_DAY, first=(12, 25)) + ticks(NEXT_DAY))

    assert run[-1][1]["status"] == "closed" and run[-1][1]["exit_reason"] == "time"
    assert order_sequence(api) == ENTRY_ORDERS + EXIT_ORDERS
    assert len(trade_rows(tmp_path)) == 1
    assert_flat(api)


def test_an_app_outage_sends_nothing_and_a_recovery_closes_the_trade_once(tmp_path):
    api, notes = Broker(), []
    bot = make_bot(tmp_path, api, notes)
    bot.enter_spread(EXPIRY, ENTRY_AT, NO_HOLIDAYS, FRESH_VIX)
    run_checks(bot, ticks(ENTRY_DAY, last=(10, 40)), stop_on_close=False)
    sent_before, notes_before = len(placed(api)), len(notes)

    failed = 0
    api.down = True
    for moment in (
        datetime(2026, 11, 9, 10, 45),
        datetime(2026, 11, 9, 10, 50),
        datetime(2026, 11, 9, 10, 55),
    ):
        with pytest.raises(httpx.ConnectError):
            bot.check_spread(moment, NO_HOLIDAYS)
        failed += 1
    api.down = False

    assert len(placed(api)) == sent_before
    assert len(notes) - notes_before <= failed  # at most one alert per failed check
    assert bot.state()["status"] == "open"

    run = run_checks(bot, ticks(ENTRY_DAY, first=(11, 0)) + ticks(NEXT_DAY))
    assert run[-1][1]["status"] == "closed" and run[-1][1]["exit_reason"] == "time"
    assert order_sequence(api) == ENTRY_ORDERS + EXIT_ORDERS
    assert len(trade_rows(tmp_path)) == 1
    assert_flat(api)


def test_a_missed_1500_check_and_a_1505_check_gives_a_late_time_exit(tmp_path):
    api, notes = Broker(), []
    bot = make_bot(tmp_path, api, notes)
    bot.enter_spread(EXPIRY, ENTRY_AT, NO_HOLIDAYS, FRESH_VIX)
    schedule = ticks(ENTRY_DAY) + ticks(NEXT_DAY, last=(14, 55)) + [datetime(2026, 11, 10, 15, 5)]

    run = run_checks(bot, schedule)

    assert run[-1][0] == datetime(2026, 11, 10, 15, 5)
    assert run[-1][1]["status"] == "closed" and run[-1][1]["exit_reason"] == "time"
    assert run[-1][1]["exit_note"] == "late"
    assert order_sequence(api) == ENTRY_ORDERS + EXIT_ORDERS
    rows = trade_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["exit_note"] == "late"
    assert_flat(api)


def test_a_skipped_entry_leaves_a_skipped_state_and_the_next_day_still_enters(tmp_path):
    api, notes = Broker(), []
    bot = make_bot(tmp_path, api, notes)
    skipped = bot.enter_spread(EXPIRY, ENTRY_AT, NO_HOLIDAYS, (ENTRY_DAY - timedelta(days=3), 20.0))
    assert skipped["status"] == "skipped" and skipped["reason"] == rule.REASON_VIX_HIGH
    assert bot.state()["status"] == "skipped" and not placed(api)
    assert bot.check_spread(ticks(ENTRY_DAY)[0], NO_HOLIDAYS) == {"status": "skipped"}
    assert "no entry today" in notes[0]

    next_entry = datetime(2026, 11, 10, 10, 16)
    entered = bot.enter_spread(EXPIRY, next_entry, NO_HOLIDAYS, (ENTRY_DAY, 14.0))
    assert entered["status"] == "open" and entered["entry_date"] == NEXT_DAY.isoformat()

    run = run_checks(bot, ticks(NEXT_DAY) + ticks(THIRD_DAY))
    assert run[-1][1]["status"] == "closed" and run[-1][1]["exit_reason"] == "time"
    assert order_sequence(api) == ENTRY_ORDERS + EXIT_ORDERS
    rows = trade_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["entry_date"] == NEXT_DAY.isoformat()
    assert_flat(api)


def test_the_ledger_stop_refuses_entry_after_a_20000_net_loss_in_the_csv(tmp_path):
    trades = tmp_path / "db" / "trades.csv"
    atm.append_trade(trades, {"entry_date": "2026-10-01", "sold": "A", "gross_rupees": -10_000})
    atm.append_trade(trades, {"entry_date": "2026-10-02", "sold": "B", "gross_rupees": -10_000})
    api, notes = Broker(), []
    bot = make_bot(tmp_path, api, notes)

    with pytest.raises(sb.Refused) as refused:
        bot.enter_spread(EXPIRY, ENTRY_AT, NO_HOLIDAYS, FRESH_VIX)

    assert str(refused.value) == atm.LEDGER_STOP_MESSAGE
    assert "lost 20,000" in notes[0]
    assert not placed(api) and not bot.path.exists()
    assert len(trade_rows(tmp_path)) == 2
