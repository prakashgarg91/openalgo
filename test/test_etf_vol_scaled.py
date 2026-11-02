"""Volatility-scaled equity and gold (trial 320): the registered rule, gates and one-run guard."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services.algos import etf_ledger as el
from services.algos import etf_vol_scaled as vs

N, G = el.NIFTY, el.GOLD


def data(days=900, seed=5, vix_level=15.0):
    idx = pd.bdate_range("2021-01-04", periods=days)
    out = {}
    for name, s in ((N, seed), (G, seed + 9)):
        r = np.random.default_rng(s).normal(0.0004, 0.01, days)
        out[name] = 100 * np.exp(np.cumsum(r))
    return pd.DataFrame(out, index=idx), pd.Series(vix_level, index=idx)


def test_sigma_is_the_mean_of_vix_and_realised_volatility():
    c, v = data()
    i = 400
    window = np.log(c[N].iloc[i - 20 : i + 1].to_numpy())
    realised = np.std(np.diff(window), ddof=1) * np.sqrt(252)
    assert vs.sigma(c, v, i) == pytest.approx((0.15 + realised) / 2)


def test_sigma_waits_for_twenty_sessions_and_a_vix_level():
    c, v = data()
    assert vs.sigma(c, v, 10) is None
    assert vs.sigma(c, v.drop(c.index[100]), 100) is None


def test_equity_weight_is_capped_and_scaled():
    assert vs.equity_weight(0.05) == 0.80
    assert vs.equity_weight(0.30) == pytest.approx(0.4)


def test_first_signal_is_the_first_month_end_after_warmup():
    c, _ = data()
    day = pd.Timestamp(vs.first_signal(c))
    i = c.index.get_loc(day)
    assert i >= vs.WARMUP_SESSIONS and el.is_month_end(c, i)
    assert not any(el.is_month_end(c, j) for j in range(vs.WARMUP_SESSIONS, i))


def test_screen_runs_and_reports_every_gate():
    c, v = data()
    out = vs.run_screen(c, v)
    assert set(out["gates"]) == {
        "net_positive_at_both_costs",
        "drawdown_and_worst_day_within_limit",
        "beats_matched_hold_at_both_costs",
        "excess_positive_in_each_half",
        "bootstrap_bound_above_zero",
        "excess_positive_without_best_month",
    }
    assert out["verdict"] == (
        "eligible for a forward shadow ledger" if all(out["gates"].values()) else "rejected"
    )
    assert out["ledger"]["double"]["cost"] >= out["ledger"]["base"]["cost"]
    w = out["matched_hold"]["weights"]
    assert 0 < w[N] <= 1 and 0 < w[G] <= 1


def test_the_screen_is_deterministic():
    c, v = data()
    assert vs.run_screen(c, v) == vs.run_screen(c, v)


def test_calm_market_holds_the_cap_and_never_rebalances_inside_the_band():
    c, v = data(vix_level=5.0)  # forecast low -> weight pinned at the cap
    out = vs.run_screen(c, v)
    assert (
        out["ledger"]["base"]["trading_sessions"] <= 1 + 60
    )  # first buy plus band-limited drift trades


def test_a_missing_close_blocks_the_screen():
    c, v = data()
    c.iloc[50, 0] = np.nan
    with pytest.raises(el.Blocked):
        vs.run_screen(c, v)


def _script():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "algo_backtest"
        / "screen_vol_scaled_etf.py"
    )
    spec = importlib.util.spec_from_file_location("screen_vol_scaled_etf", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_second_run_is_refused_in_words():
    mod = _script()
    assert mod.refusal(date(2026, 11, 2), report_exists=False, marker_committed=False) is None
    for kwargs in (
        {"report_exists": True, "marker_committed": False},
        {"report_exists": False, "marker_committed": True},
    ):
        text = mod.refusal(date(2026, 11, 2), **kwargs)
        assert text and "already" in text
