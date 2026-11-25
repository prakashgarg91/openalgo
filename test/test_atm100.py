from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

from scripts.algo_backtest import atm100_replay
from scripts.algo_backtest.atm100_shadow_ledger import build_ledger
from services.algos import atm100_rule as rule

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 11, 30)
NEXT = date(2026, 12, 1)
EXPIRY = NEXT
SOLD = "NIFTY01DEC2625000CE"
LONG = "NIFTY01DEC2625100CE"


def _candle(day: date, clock: time, close: float) -> dict:
    return {
        "timestamp": int(datetime.combine(day, clock, tzinfo=IST).timestamp()),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1,
    }


def _reader_for(exit_spreads: list[tuple[date, time, float]], missing: set[str] | None = None):
    missing = missing or set()
    data: dict[str, list[dict]] = {
        "NIFTY": [_candle(DAY, time(10, 15), 25000)],
        SOLD: [_candle(DAY, time(10, 15), 10)],
        LONG: [_candle(DAY, time(10, 15), 1)],
    }
    for d, clock, spread in exit_spreads:
        data[SOLD].append(_candle(d, clock, spread + 1))
        data[LONG].append(_candle(d, clock, 1))

    def reader(symbol, exchange, interval, start_ts, end_ts):
        if symbol in missing:
            return pd.DataFrame()
        rows = data.get(symbol, [])
        return pd.DataFrame([row for row in rows if start_ts <= row["timestamp"] <= end_ts])

    return reader


def _build(reader, through=DAY):
    return build_ledger(
        DAY,
        through,
        reader,
        lambda _day, _exchange: False,
        lambda _day: 15.0,
        cost_function=lambda *_args: 0.0,
        expiry_picker=lambda _day, _holiday: EXPIRY,
    )


def test_entry_floor_and_vix_gate():
    floor = rule.plan_entry(25012, 19.9, 3.0, 0.0)
    assert floor.skipped_reason == rule.REASON_CREDIT_SMALL
    taken = rule.plan_entry(25012, 19.9, 3.1, 0.0)
    assert taken.skipped_reason is None
    assert taken.sold_strike == 25000
    assert taken.bought_strike == 25100
    assert rule.plan_entry(25000, 20.0, 10.0, 1.0).skipped_reason == rule.REASON_VIX_HIGH


def test_shadow_ledger_target_exit():
    rows = _build(_reader_for([(DAY, time(10, 16), 1.0)]))
    assert rows[0]["status"] == "closed"
    assert rows[0]["exit_reason"] == "target"
    assert rows[0]["exit_value"] == 1.0
    assert rows[0]["net"] == 520.0


def test_shadow_ledger_stop_exit():
    rows = _build(_reader_for([(DAY, time(10, 16), 30.0)]))
    assert rows[0]["exit_reason"] == "stop"
    assert rows[0]["exit_value"] == 30.0
    assert rows[0]["net"] == -1365.0


def test_shadow_ledger_time_exit_and_one_position_rule():
    rows = _build(
        _reader_for([(DAY, time(10, 16), 10.0), (NEXT, time(15, 0), 4.0)]),
        through=NEXT,
    )
    assert rows[0]["exit_reason"] == "time"
    assert rows[0]["exit_time"] == "2026-12-01 15:00"
    assert rows[1]["status"] == "skipped"
    assert "position was open" in rows[1]["note"]


def test_missing_option_candles_are_no_data():
    rows = _build(_reader_for([], missing={LONG}))
    assert rows[0]["status"] == "no_data"
    assert "10:15 closes" in rows[0]["note"]


def test_replay_module_imports_without_running_replay():
    assert atm100_replay.VARIANTS == (
        "base",
        "a_entry_open",
        "b_entry_next",
        "c_intrabar_stop",
        "d_exit_next_bar",
        "e_all",
    )


def test_a_trade_with_missing_data_does_not_stop_the_ledger_for_good():
    # No option closes after entry: that trade is no_data, the next session is blocked as if it were held,
    # and the session after that is judged on its own again instead of being held back for good.
    rows = _build(_reader_for([]), through=date(2026, 12, 2))
    by_day = {row["entry_date"]: (row["status"], row["note"]) for row in rows}
    assert by_day["2026-11-30"][0] == "no_data"
    assert by_day["2026-12-01"] == ("skipped", "The prior session's position was open at 10:15.")
    assert by_day["2026-12-02"][1] != "The prior session's position was open at 10:15."
