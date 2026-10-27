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


def test_conservative_costs_are_not_below_the_flat_rate_for_a_normal_condor():
    entry, exit_ = [4.0, 4.0, 40.0, 40.0], [3.0, 3.0, 30.0, 30.0]
    sells = [False, False, True, True]
    assert trade_cost(CONSERVATIVE, entry, exit_, sells) >= 300.0


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
def test_standard_model_reproduces_the_original_backtest():
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
    assert zen["trades"] == 1360 and zen["win_rate"] == 62.5 and zen["profit_factor"] == 1.49
