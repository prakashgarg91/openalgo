"""The Lab: history parsing and caching, pricing models, and the replay."""

import os
import time

import numpy as np
import pandas as pd
import pytest

from services.algos import lab
from services.algos.lab import (
    CONSERVATIVE,
    STANDARD,
    History,
    HistoryUnavailable,
    load_history,
    parse_chart,
    run_lab,
    summarize,
    trade_cost,
)


def _frame(start, days, seed, level, vol):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=days)
    close = level * np.exp(np.cumsum(rng.normal(0, vol, days)))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, vol / 3, days))
    return pd.DataFrame({"Open": open_, "Close": close}, index=idx)


@pytest.fixture
def history():
    days = 160
    return History(
        frames={
            "nifty": _frame("2024-01-01", days, 1, 22000, 0.006),
            "vix": _frame("2024-01-01", days, 2, 14, 0.03),
            "spx": _frame("2024-01-01", days, 3, 5000, 0.007),
            "ndx": _frame("2024-01-01", days, 4, 17000, 0.009),
            "crude": _frame("2024-01-01", days, 5, 80, 0.015),
            "dxy": _frame("2024-01-01", days, 6, 104, 0.003),
        }
    )


def _payload(ts, opens, closes, offset=19800):
    return {
        "chart": {
            "result": [
                {
                    "meta": {"gmtoffset": offset},
                    "timestamp": ts,
                    "indicators": {"quote": [{"open": opens, "close": closes}]},
                }
            ]
        }
    }


# --- parsing ---------------------------------------------------------------


def test_parse_chart_dates_use_the_exchange_offset_and_drop_empty_closes():
    # 03:45 UTC is 09:15 IST on 2024-01-02; the second row has no close.
    t1, t2 = 1704167700, 1704254100
    frame = parse_chart(_payload([t1, t2], [100.0, 101.0], [102.0, None]))
    assert list(frame.index.strftime("%Y-%m-%d")) == ["2024-01-02"]
    assert frame.loc["2024-01-02", "Close"] == 102.0


@pytest.mark.parametrize("payload", [{}, {"chart": {"result": None}}, _payload([], [], [])])
def test_parse_chart_refuses_unreadable_replies_in_plain_words(payload):
    with pytest.raises(HistoryUnavailable) as excinfo:
        parse_chart(payload)
    message = str(excinfo.value)
    assert "provider" in message and "Traceback" not in message and "KeyError" not in message


# --- caching ---------------------------------------------------------------


def _stub_fetch(calls, fail=False):
    def fetch(symbol):
        calls.append(symbol)
        if fail:
            raise HistoryUnavailable("down")
        return _frame("2024-01-01", 30, hash(symbol) % 1000, 100, 0.01)

    return fetch


def test_load_history_downloads_once_then_reads_the_fresh_cache(tmp_path):
    calls = []
    first = load_history(tmp_path, fetch=_stub_fetch(calls))
    assert len(calls) == len(lab.SERIES) and set(first.frames) == set(lab.SERIES)
    calls.clear()
    load_history(tmp_path, fetch=_stub_fetch(calls))
    assert calls == []


def test_load_history_refreshes_a_stale_cache(tmp_path):
    load_history(tmp_path, fetch=_stub_fetch([]))
    calls = []
    load_history(tmp_path, fetch=_stub_fetch(calls), now=lambda: time.time() + 48 * 3600)
    assert len(calls) == len(lab.SERIES)


def test_a_failed_refresh_falls_back_to_the_saved_copy_and_says_so(tmp_path):
    load_history(tmp_path, fetch=_stub_fetch([]))
    result = load_history(
        tmp_path, fetch=_stub_fetch([], fail=True), now=lambda: time.time() + 48 * 3600
    )
    assert set(result.frames) == set(lab.SERIES)
    assert result.notes and "saved" in result.notes[0]


def test_no_cache_and_no_connection_is_a_clear_error(tmp_path):
    with pytest.raises(HistoryUnavailable):
        load_history(tmp_path, fetch=_stub_fetch([], fail=True))


# --- statistics and costs --------------------------------------------------


def test_summarize_known_values():
    m = summarize([100.0, -50.0, 200.0, -300.0, 50.0])
    assert m["trades"] == 5 and m["win_rate"] == 60.0
    assert m["total"] == 0.0 and m["worst"] == -300.0 and m["best"] == 200.0
    assert m["profit_factor"] == 1.0
    assert m["max_drawdown"] == -300.0  # peak 250, then down to -50


def test_summarize_drawdown_is_the_deepest_fall_from_a_peak():
    assert summarize([100, 100, -50, -60, 30])["max_drawdown"] == -110.0


def test_summarize_empty_is_safe():
    assert summarize([])["trades"] == 0 and summarize([])["profit_factor"] is None


def test_flat_cost_ignores_the_legs_and_the_conservative_cost_grows_with_premium():
    assert trade_cost(STANDARD, [10.0], [8.0], [True]) == 300.0
    cheap = trade_cost(CONSERVATIVE, [2.0, 1.0], [1.0, 1.0], [False, True])
    dear = trade_cost(CONSERVATIVE, [80.0, 60.0], [70.0, 50.0], [False, True])
    assert cheap > 0 and dear > cheap


def test_itemised_cost_of_a_cheap_condor_is_a_realistic_nifty_figure():
    entry, exit_ = [4.0, 4.0, 40.0, 40.0], [3.0, 3.0, 30.0, 30.0]
    cost = trade_cost(CONSERVATIVE, entry, exit_, [False, False, True, True])
    assert 150 <= cost <= 400


# --- replay ----------------------------------------------------------------


@pytest.mark.parametrize("algo", ["zen", "mirror_zen", "calm_condor", "morning_gap"])
@pytest.mark.parametrize("model", ["standard", "conservative"])
def test_every_algo_replays_on_both_models(history, algo, model):
    result = run_lab(history, algo, model=model)
    assert result.model == model and result.days > 0
    assert len(result.curve) == len(result.trades)
    assert result.metrics["trades"] == len(result.trades)
    assert result.metrics["trades"] + sum(result.skipped.values()) <= result.days


def test_replay_is_deterministic(history):
    a = run_lab(history, "zen")
    b = run_lab(history, "zen")
    assert a.trades == b.trades and a.metrics == b.metrics


def test_the_regime_gate_only_removes_trades(history):
    gated = run_lab(history, "zen", gated=True)
    ungated = run_lab(history, "zen", gated=False)
    assert ungated.metrics["trades"] >= gated.metrics["trades"]
    gated_dates = {t["date"] for t in gated.trades}
    assert gated_dates <= {t["date"] for t in ungated.trades}


def test_the_date_range_is_respected(history):
    result = run_lab(history, "zen", start="2024-03-01", end="2024-04-30")
    assert result.trades and all("2024-03-01" <= t["date"] <= "2024-04-30" for t in result.trades)


def test_skips_are_counted_with_a_reason(history):
    result = run_lab(history, "mirror_zen")
    assert result.skipped and all(isinstance(k, str) and v > 0 for k, v in result.skipped.items())


def test_unknown_algo_or_model_raises(history):
    with pytest.raises(KeyError):
        run_lab(history, "nope")
    with pytest.raises(KeyError):
        run_lab(history, "zen", model="optimistic")


def test_each_trade_loses_no_more_than_the_spread_width_allows(history):
    # Width 150 points x 75 = 11,250 per lot, plus costs. A bigger loss means a pricing bug.
    for algo in ("zen", "calm_condor", "morning_gap"):
        result = run_lab(history, algo, model="conservative", gated=False)
        assert all(t["pnl"] > -11_250 - 800 for t in result.trades), algo


# --- the old numbers, when the data is at hand -----------------------------

EQUIV_DIR = os.getenv("ALGO_LAB_EQUIV_DIR")


@pytest.mark.skipif(not EQUIV_DIR, reason="needs the 2018-2026 CSVs from scripts/algo_backtest")
def test_standard_model_still_gives_the_recorded_result_on_the_real_history():
    def load(name):
        df = pd.read_csv(f"{EQUIV_DIR}/{name}.csv", index_col=0, parse_dates=True)
        df.index = df.index.tz_localize(None) if df.index.tz else df.index
        return df

    h = History(
        {
            k: load(v)
            for k, v in {
                "nifty": "nsei",
                "vix": "vix",
                "spx": "spx",
                "ndx": "ndx",
                "crude": "crude",
                "dxy": "dxy",
            }.items()
        }
    )
    zen = run_lab(h, "zen", model="standard", start="2018-01-01").metrics
    # The original script gave 1360 trades, 62.5 percent and 1.49 before overnight algos
    # skipped the days before expiry; with that rule the same data gives these.
    assert zen["trades"] == 798 and zen["win_rate"] == 70.1 and zen["profit_factor"] == 1.91


def test_every_trade_reports_its_cost_and_the_break_even_is_the_gross_edge(history):
    result = run_lab(history, "calm_condor", model="conservative", gated=False)
    assert result.trades and all(t["cost"] > 0 for t in result.trades)
    m = result.metrics
    assert m["avg_gross"] == pytest.approx(m["avg"] + m["avg_cost"], abs=0.2)
    assert m["break_even_cost"] == max(0.0, m["avg_gross"])


def test_conservative_cost_for_a_condor_is_a_realistic_nifty_figure():
    # Four legs, shorts near 70 points, longs near 12. Liquid weekly Nifty options:
    # a few hundred rupees per lot, not thousands.
    cost = trade_cost(
        CONSERVATIVE, [12.0, 12.0, 70.0, 70.0], [10.0, 10.0, 55.0, 55.0], [False, False, True, True]
    )
    assert 250 <= cost <= 700


def test_the_trading_clock_gives_a_weekend_one_session_of_decay_not_three_days():
    fri, mon, thu = (
        pd.Timestamp("2024-03-01"),
        pd.Timestamp("2024-03-04"),
        pd.Timestamp("2024-03-07"),
    )
    assert lab._years(STANDARD, fri, mon) == pytest.approx(3 / 365)
    assert lab._years(CONSERVATIVE, fri, mon) == pytest.approx(1 / 252)
    # Friday to the next Thursday is four sessions on the trading clock.
    assert lab._years(CONSERVATIVE, fri, thu) == pytest.approx(4 / 252)


def test_only_the_conservative_model_uses_the_trading_clock():
    assert CONSERVATIVE.trading_clock and not STANDARD.trading_clock


def test_a_research_plan_function_replaces_the_catalogue_rules(history):
    from services.algos.templates import Plan, condor_config

    calls = []

    def plan_fn(regime, inputs, dte, extra):
        calls.append(extra)
        cfg = condor_config("x", 1, "weekly", short_offset="OTM1", long_offset="OTM3")
        return Plan("calm_condor", "trade", "r", cfg, 1, 0.0, "iron_condor")

    result = run_lab(history, "calm_condor", plan_fn=plan_fn, model="standard")
    assert result.metrics["trades"] > 0 and not result.skipped
    assert all({"date", "vix_rank"} <= set(extra) for extra in calls)


def test_iv_scale_cheapens_every_option_and_defaults_to_the_vix_level():
    import dataclasses

    assert STANDARD.iv_scale == 1.0 and CONSERVATIVE.iv_scale == 1.0
    cheaper = dataclasses.replace(STANDARD, iv_scale=0.8)
    assert lab._leg_vol(cheaper, 0.15, "PE", 2) == pytest.approx(0.12)
    assert lab._leg_vol(STANDARD, 0.15, "PE", 2) == pytest.approx(0.15)


def test_overnight_variance_share_is_a_fraction_and_matches_a_known_series():
    idx = pd.bdate_range("2024-01-01", periods=4)
    # Overnight moves of +1 percent, intraday moves of zero: all variance is overnight.
    frame = pd.DataFrame(
        {"Open": [100.0, 101.0, 102.01, 103.03], "Close": [100.0, 101.0, 102.01, 103.03]}, index=idx
    )
    assert lab.overnight_variance_share(frame) > 0.99
    # Every open equals the previous close, so nothing happens overnight.
    closes = [100.0, 101.0, 100.0, 102.0, 101.0]
    no_gaps = pd.DataFrame(
        {"Open": [100.0] + closes[:-1], "Close": closes},
        index=pd.bdate_range("2024-01-01", periods=5),
    )
    assert lab.overnight_variance_share(no_gaps) == pytest.approx(0.0, abs=1e-12)


def test_only_the_conservative_model_uses_the_variance_clock():
    assert CONSERVATIVE.variance_clock and not STANDARD.variance_clock


def test_the_variance_clock_cuts_what_an_overnight_seller_earns(history):
    import dataclasses

    base = dataclasses.replace(CONSERVATIVE, name="vc_off", variance_clock=False)
    lab.MODELS["vc_off"] = base
    try:
        with_clock = run_lab(history, "calm_condor", model="conservative", gated=False)
        without = run_lab(history, "calm_condor", model="vc_off", gated=False)
    finally:
        del lab.MODELS["vc_off"]
    assert with_clock.metrics["avg_gross"] < without.metrics["avg_gross"]


# --- real option prices ----------------------------------------------------


def _real_day(day, expiry, rows):
    """rows: (strike, kind, open, close, volume)."""
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp(day),
                "expiry": pd.Timestamp(expiry),
                "strike": k,
                "kind": kind,
                "open": o,
                "close": c,
                "volume": v,
            }
            for k, kind, o, c, v in rows
        ]
    )


def test_real_prices_mark_is_close_on_entry_day_and_open_on_exit_day():
    real = lab.RealPrices(
        {
            pd.Timestamp("2024-03-01"): _real_day(
                "2024-03-01", "2024-03-07", [(22000, "PE", 90.0, 80.0, 500)]
            ),
            pd.Timestamp("2024-03-04"): _real_day(
                "2024-03-04", "2024-03-07", [(22000, "PE", 70.0, 60.0, 400)]
            ),
        }
    )
    assert real.mark("2024-03-01", "2024-03-04", "2024-03-07", 22000, "PE") == (80.0, 70.0)
    assert real.expiries("2024-03-01") == [pd.Timestamp("2024-03-07")]


@pytest.mark.parametrize(
    "entry_row,exit_row",
    [
        ((22000, "PE", 90.0, 0.0, 500), (22000, "PE", 70.0, 60.0, 400)),  # no entry close
        ((22000, "PE", 90.0, 80.0, 0), (22000, "PE", 70.0, 60.0, 400)),  # entry day not traded
        ((22000, "PE", 90.0, 80.0, 500), (22000, "PE", 0.0, 60.0, 400)),  # no opening print
        ((22000, "PE", 90.0, 80.0, 500), (22050, "PE", 70.0, 60.0, 400)),  # contract absent
    ],
)
def test_a_contract_without_a_real_print_is_missing_never_filled_in(entry_row, exit_row):
    real = lab.RealPrices(
        {
            pd.Timestamp("2024-03-01"): _real_day("2024-03-01", "2024-03-07", [entry_row]),
            pd.Timestamp("2024-03-04"): _real_day("2024-03-04", "2024-03-07", [exit_row]),
        }
    )
    assert real.mark("2024-03-01", "2024-03-04", "2024-03-07", 22000, "PE") is None


def test_a_real_price_replay_uses_only_actual_prices_and_counts_what_it_cannot_price(history):
    # One real day pair covering the first usable date; everything else has no option data.
    nifty = history.frames["nifty"]
    d0, d1 = nifty.index[40], nifty.index[41]
    spot = float(nifty["Close"].iloc[40])
    atm = round(spot / 50) * 50
    expiry = d0 + pd.Timedelta(days=4)
    rows0 = [(atm - 50 * n, "PE", 0, 10.0 + n, 100) for n in (1, 4)] + [
        (atm + 50 * n, "CE", 0, 10.0 + n, 100) for n in (1, 4)
    ]
    rows1 = [(atm - 50 * n, "PE", 5.0, 0, 0) for n in (1, 4)] + [
        (atm + 50 * n, "CE", 5.0, 0, 0) for n in (1, 4)
    ]
    real = lab.RealPrices({d0: _real_day(d0, expiry, rows0), d1: _real_day(d1, expiry, rows1)})
    result = run_lab(history, "zen", model="conservative", gated=False, real=real)
    assert sum(result.skipped.values()) + len(result.trades) <= result.days
    assert result.skipped.get("No option prices for this day", 0) > 0
    for trade in result.trades:  # any priced trade must come from the two real days
        assert trade["date"] == d0.strftime("%Y-%m-%d")


# --- multi-day hold on real prices -------------------------------------------


def _hold_world(history, hold_day_index):
    """Real prices on entry day d0, the next day d1 and a later day dk, all for one expiry."""
    nifty = history.frames["nifty"]
    d0, d1, dk = nifty.index[40], nifty.index[41], nifty.index[40 + hold_day_index]
    spot = float(nifty["Close"].iloc[40])
    atm = round(spot / 50) * 50
    expiry = nifty.index[40 + hold_day_index] + pd.Timedelta(days=2)
    entry = [(atm - 50 * n, "PE", 0, 20.0 - n, 100) for n in (1, 4)]
    one_night = [(atm - 50 * n, "PE", 15.0 - n, 0, 0) for n in (1, 4)]
    later = [(atm - 50 * n, "PE", 6.0 - n, 0, 0) for n in (1, 4)]
    days = {d0: _real_day(d0, expiry, entry), d1: _real_day(d1, expiry, one_night)}
    days[dk] = _real_day(dk, expiry, later)
    return d0, d1, dk, lab.RealPrices(days)


def _one_leg_plan(regime, inputs, dte, extra):
    from services.algos.templates import Plan, spread_config

    cfg = spread_config("c", "bull_put", 1, "weekly", short_offset="OTM1", long_offset="OTM4")
    return Plan("zen", "trade", "", cfg, 1, 0.0, "bull_put")


def test_holding_longer_prices_the_exit_from_the_later_day(history):
    d0, d1, dk, real = _hold_world(history, 3)
    one = run_lab(history, "zen", gated=False, real=real, plan_fn=_one_leg_plan, hold=1)
    three = run_lab(history, "zen", gated=False, real=real, plan_fn=_one_leg_plan, hold=3)
    day = d0.strftime("%Y-%m-%d")
    pnl_one = next(t["pnl"] for t in one.trades if t["date"] == day)
    pnl_three = next(t["pnl"] for t in three.trades if t["date"] == day)
    assert pnl_one != pnl_three
    # Short OTM1 leg decayed 19 -> 14 overnight and 19 -> 5 over three days: the longer hold
    # kept more of the premium before costs.
    assert pnl_three > pnl_one


def test_a_hold_longer_than_a_night_needs_real_prices(history):
    with pytest.raises(ValueError):
        run_lab(history, "zen", hold=2)
    with pytest.raises(ValueError):
        run_lab(history, "zen", hold=0)


def test_a_hold_with_no_price_on_the_exit_day_is_skipped_and_counted(history):
    d0, d1, dk, real = _hold_world(history, 3)
    real._days.pop(dk)
    result = run_lab(history, "zen", gated=False, real=real, plan_fn=_one_leg_plan, hold=3)
    assert result.skipped.get("No option prices for this day", 0) > 0
    assert not any(t["date"] == d0.strftime("%Y-%m-%d") for t in result.trades)
