"""Forward shadow test of the three registered side rules (no broker, no database, no orders)."""

import numpy as np
import pandas as pd
import pytest

from services.algos import forward_shadow as fs
from services.algos.intraday import OptionBars

EXPIRY = pd.Timestamp("2026-11-03")
PREV, D1, D2 = (pd.Timestamp(d) for d in ("2026-10-28", "2026-10-29", "2026-10-30"))


def minutes(day):
    return pd.date_range(day + pd.Timedelta(hours=9, minutes=15), periods=375, freq="1min")


def index_frame(closes, opens=None):
    """Nifty 1-minute candles per day. ``closes`` and ``opens`` map day -> function of minute index."""
    rows = []
    for day, close_fn in closes.items():
        for i, ts in enumerate(minutes(day)):
            close = close_fn(i)
            open_ = (opens or {}).get(day, close_fn)(i) if i == 0 else close
            rows.append((ts, open_, max(open_, close), min(open_, close), close))
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"]).set_index(
        "timestamp"
    )


def leg(days, price_fn):
    """One option leg: price_fn(day, minute_index) -> price."""
    rows = []
    for day in days:
        for i, ts in enumerate(minutes(day)):
            price = price_fn(day, i)
            rows.append((ts, price, price, price, price))
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"]).set_index(
        "timestamp"
    )


def bars_for(sold_fn, long_fn, kinds=("CE", "PE"), days=(D1, D2), strikes=(25000.0,)):
    frames = {}
    for kind in kinds:
        for strike in strikes:
            frames[(EXPIRY, kind, strike)] = leg(days, sold_fn)
            far = strike + 400 if kind == "CE" else strike - 400
            frames[(EXPIRY, kind, far)] = leg(days, long_fn)
    return OptionBars(frames)


VIX = pd.Series([13.0], index=[PREV])
FLAT = lambda i: 25012.0  # noqa: E731


def quiet_index(prev_close=25012.0, today=FLAT, today_open=None):
    return index_frame(
        {PREV: lambda i: prev_close, D1: today, D2: FLAT},
        opens={D1: today_open or today},
    )


def test_side_rules_truth_table():
    assert fs.choose_side("A", 101, 100, 100) == "PE"
    assert fs.choose_side("A", 101, 100, 102) == "CE"
    assert fs.choose_side("A", 100, 100, 99) == "CE"  # equality takes the other branch
    assert fs.choose_side("B", 100, 100, 99) == "PE"  # at or below the open
    assert fs.choose_side("B", 101, 100, 99) == "CE"
    assert fs.choose_side("C", 90, 100, 120) == "CE"
    with pytest.raises(ValueError):
        fs.choose_side("D", 1, 1, 1)


def test_session_facts_report_what_is_missing():
    index = quiet_index()
    entry = D1 + pd.Timedelta(hours=10, minutes=15)
    assert fs.session_facts(index, D1, entry) == (25012.0, 25012.0, 25012.0)
    assert fs.session_facts(index.drop(entry - fs.STEP), D1, entry) == "no 10:14 candle"
    assert (
        fs.session_facts(index[index.index.normalize() != PREV], D1, entry) == "no previous close"
    )
    late = index[
        ~((index.index.normalize() == D1) & (index.index.time < pd.Timestamp("09:20").time()))
    ]
    assert fs.session_facts(late, D1, entry) == "no 09:15 candle"


def test_rule_c_sells_a_call_spread_and_leaves_at_three_the_next_day():
    bars = bars_for(lambda d, i: 100.0, lambda d, i: 20.0)
    result = fs.simulate_rule("C", bars, quiet_index(), VIX)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade["side"] == "CE" and trade["reason"] == "time"
    assert trade["entry"] == D1 + pd.Timedelta(hours=10, minutes=15)
    assert trade["exit"] == D2 + pd.Timedelta(hours=15)
    assert trade["sold"] == 25000.0 and trade["long"] == 25400.0
    assert trade["net"] == pytest.approx(trade["pts"] * trade["lot"] - trade["cost"])
    assert result.skipped["no prices"] == 0


def test_a_stop_reverses_to_the_other_side_with_the_same_exits():
    def sold(kind):
        # the call leg jumps 60 points at 11:00 on the first day, the put leg stays put
        return lambda d, i: 160.0 if (kind == "CE" and d == D1 and i >= 105) else 100.0

    frames = {}
    for kind in ("CE", "PE"):
        frames[(EXPIRY, kind, 25000.0)] = leg((D1, D2), sold(kind))
        far = 25400.0 if kind == "CE" else 24600.0
        frames[(EXPIRY, kind, far)] = leg((D1, D2), lambda d, i: 20.0)
    result = fs.simulate_rule("C", OptionBars(frames), quiet_index(), VIX)
    first, second = result.trades[0], result.trades[1]
    assert first["reason"] == "stop" and first["side"] == "CE" and first["reversal"] == 0
    assert second["side"] == "PE" and second["reversal"] == 1
    assert second["episode"] == first["episode"]
    assert second["entry"] == first["exit"] + fs.STEP


def test_a_high_vix_or_a_gap_down_means_no_entry():
    bars = bars_for(lambda d, i: 100.0, lambda d, i: 20.0)
    high = fs.simulate_rule("C", bars, quiet_index(), pd.Series([21.0, 21.0], index=[PREV, D1]))
    assert not high.trades and high.skipped["vix ceiling"] == 2  # both stored sessions
    gap = fs.simulate_rule("C", bars, quiet_index(prev_close=25400.0), VIX)
    assert not gap.trades and gap.skipped["gap down"] == 1
    none = fs.simulate_rule("C", bars, quiet_index(), pd.Series(dtype=float))
    assert none.skipped["no vix"] == 2


def test_a_stale_or_missing_vix_never_gates_a_day():
    bars = bars_for(lambda d, i: 100.0, lambda d, i: 20.0)
    # VIX stored for the day before D1 only: D2's previous session (D1) has none, so D2 has no entry
    result = fs.simulate_rule("C", bars, quiet_index(), pd.Series([13.0], index=[PREV]))
    assert result.skipped["no vix"] == 0  # D2 is blocked by the open position, not by VIX
    only_d2 = bars_for(lambda d, i: 100.0, lambda d, i: 20.0, days=(D2,))
    stale = fs.simulate_rule("C", only_d2, quiet_index(), pd.Series([13.0], index=[PREV]))
    assert stale.skipped["no vix"] == 1 and not stale.trades
    nan = fs.simulate_rule("C", bars, quiet_index(), pd.Series([np.nan], index=[PREV]))
    assert nan.skipped["no vix"] >= 1 and not nan.trades


def test_a_partly_stored_previous_day_is_not_a_previous_session():
    index = quiet_index()
    short = index[
        ~((index.index.normalize() == PREV) & (index.index.time > pd.Timestamp("14:00").time()))
    ]
    entry = D1 + pd.Timedelta(hours=10, minutes=15)
    assert fs.previous_session(short, D1) is None
    assert fs.session_facts(short, D1, entry) == "no previous close"
    assert fs.previous_session(index, D1) == PREV


def test_rules_a_and_b_choose_differently_on_a_rising_morning():
    rising = lambda i: 25000.0 + min(i, 60)  # noqa: E731  rises from the open, ends above the prior close
    bars = bars_for(lambda d, i: 100.0, lambda d, i: 20.0, strikes=(25050.0,))
    index = quiet_index(prev_close=25000.0, today=rising, today_open=lambda i: 25000.0)
    a = fs.simulate_rule("A", bars, index, VIX)
    b = fs.simulate_rule("B", bars, index, VIX)
    assert a.trades[0]["side"] == "PE" and b.trades[0]["side"] == "CE"


def test_a_position_still_held_is_open_not_a_trade_and_marks_the_equity():
    bars = bars_for(lambda d, i: 90.0 if d == D1 else 100.0, lambda d, i: 20.0, days=(D1,))
    result = fs.simulate_rule("C", bars, quiet_index(), VIX)
    assert not result.trades and len(result.open_positions) == 1
    assert fs.episodes_closed(result) == 0
    equity = fs.equity_curve(result, [D1])
    credit = 90.0 - 20.0
    assert equity.iloc[0] == pytest.approx((credit - (90.0 - 20.0)) * 65)  # marked flat


def test_equity_marks_a_move_and_counts_the_worst_point_inside_the_session():
    def sold(d, i):
        return (
            100.0 if i < 200 else (140.0 if i == 200 else 80.0)
        )  # a spike at one candle, then a fall

    bars = bars_for(sold, lambda d, i: 20.0, days=(D1,))
    result = fs.simulate_rule(
        "C", bars, quiet_index(), VIX, rules=fs.replace_rules(stop_pts=None, target_pts=None)
    )
    paths = fs.equity_paths(result, [D1])
    credit = 100.0 - 20.0
    assert paths["eod"].iloc[0] == pytest.approx(
        (credit - (80.0 - 20.0)) * 65
    )  # a gain of 20 points
    assert paths["low"].iloc[0] == pytest.approx(
        (credit - (140.0 - 20.0)) * 65
    )  # the spike is the low
    assert paths["low"].iloc[0] < paths["eod"].iloc[0]
    assert fs.max_drawdown(paths) == pytest.approx(-paths["low"].iloc[0])
    assert fs.worst_day(paths) == pytest.approx(paths["low"].iloc[0])


def test_drawdown_and_the_daily_cap_use_the_worst_point():
    paths = pd.DataFrame(
        {"eod": [5000.0, 3000.0, 9000.0], "low": [4000.0, -18000.0, 8000.0]},
        index=pd.date_range("2026-10-29", periods=3),
    )
    assert fs.max_drawdown(paths) == pytest.approx(23000.0)  # from the 5,000 peak down to -18,000
    assert fs.worst_day(paths) == pytest.approx(
        -23000.0
    )  # from the 5,000 close to -18,000 inside day 2


def test_bootstrap_bound_is_fixed_and_signs_are_right():
    gains = np.full(60, 100.0)
    assert fs.block_bootstrap_lower(gains) == pytest.approx(100.0)
    assert fs.block_bootstrap_lower(gains) == fs.block_bootstrap_lower(gains)
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 500, 60)
    assert fs.block_bootstrap_lower(noise) < 0 < fs.block_bootstrap_lower(noise + 5000)
    assert fs.block_bootstrap_lower(np.zeros(60)) == 0.0


def test_evaluate_is_not_final_before_252_sessions_and_never_passes_with_no_trades():
    bars = bars_for(lambda d, i: 100.0, lambda d, i: 20.0)
    days = [D1, D2]
    results = {r: fs.simulate_rule(r, bars, quiet_index(), VIX) for r in fs.SIDE_RULES}
    report = fs.evaluate(results, days)
    assert report["final"] is False and report["sessions"] == 2
    for name in fs.CANDIDATES:
        assert report[name]["all_gates"] is False
        assert report[name]["gates"]["episodes"] is False  # one episode is far under 100


def test_contract_names_and_stored_rows_are_read_correctly():
    from services.algos import forward_shadow_data as data

    assert data.parse_contract("NIFTY03NOV2625000CE") == (pd.Timestamp("2026-11-03"), "CE", 25000.0)
    assert data.parse_contract("NIFTY03NOV2622937.5PE") == (
        pd.Timestamp("2026-11-03"),
        "PE",
        22937.5,
    )
    assert data.parse_contract("BANKNIFTY03NOV2625000CE") is None
    assert data.parse_contract("NIFTY31FEB2625000CE") is None
    stored = pd.DataFrame(
        {"timestamp": [1793245500], "open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5]}
    )
    assert data.to_ist_frame(stored).index[0] == pd.Timestamp("2026-10-29 09:15:00")
    assert data.to_ist_frame(pd.DataFrame()).empty


def test_a_missing_control_fails_the_paired_gate_and_nothing_passes_before_the_end():
    bars = bars_for(lambda d, i: 100.0, lambda d, i: 20.0)
    results = {r: fs.simulate_rule(r, bars, quiet_index(), VIX) for r in ("A", "B")}
    report = fs.evaluate(results, [D1, D2])
    for name in fs.CANDIDATES:
        assert report[name]["gates"]["beats_control"] is False
        assert report[name]["all_gates"] is False
        assert report[name]["verdict"] == "not due yet"


def test_the_gap_filter_uses_a_one_percent_fall_inclusive():
    bars = bars_for(lambda d, i: 100.0, lambda d, i: 20.0)
    exactly = fs.simulate_rule("C", bars, quiet_index(prev_close=25012.0 / 0.99), VIX)
    assert exactly.skipped["gap down"] == 1
    barely = fs.simulate_rule("C", bars, quiet_index(prev_close=25012.0 / 0.9901), VIX)
    assert barely.skipped["gap down"] == 0


def test_a_stop_on_the_next_day_does_not_reverse_and_reversals_stop_at_three():
    def sold(d, i):
        return 100.0 if d == D1 or i < 30 else 200.0  # day two jumps at once: stop, not a reversal

    bars = bars_for(sold, lambda d, i: 20.0)
    nextday = fs.simulate_rule("C", bars, quiet_index(), VIX)
    assert len(nextday.trades) == 1 and nextday.trades[0]["reason"] == "stop"
    assert nextday.trades[0]["exit"].normalize() == D2

    def always_up(d, i):
        return 100.0 + 60.0 * (i // 3)  # every few minutes the sold leg reprices over the stop

    flip = bars_for(always_up, lambda d, i: 20.0, days=(D1,))
    result = fs.simulate_rule("C", flip, quiet_index(), VIX)
    assert len(result.trades) > 1
    assert max(t["reversal"] for t in result.trades) <= 3


def test_an_expiry_day_exit_at_the_last_five_minute_bar_is_a_closed_trade_only_when_told_so():
    """5-minute bars end at 15:25; the 1-minute default (15:29) treats that day as partly stored."""
    import inspect
    from datetime import time as dtime

    sig = inspect.signature(fs.simulate_rule)
    assert sig.parameters["last_bar"].default == fs.LAST_INDEX_CANDLE == dtime(15, 29)
