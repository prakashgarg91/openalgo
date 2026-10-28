"""The broader strategy families: no peeking, honest costs, and rules that do what they say."""

import numpy as np
import pandas as pd
import pytest

from services.algos import universe as u


def make_bars(days=700, seed=1, drift=0.0004, vol=0.01, start="2018-01-01"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=days)
    out = {}
    for key, s in (("equity", seed), ("gold", seed + 50)):
        r = np.random.default_rng(s).normal(drift, vol, days)
        close = 100 * np.exp(np.cumsum(r))
        open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, vol / 4, days))
        out[key] = pd.DataFrame({"Open": open_, "Close": close}, index=idx)
    return out


BARS = make_bars()


def flat_bars(close):
    df = pd.DataFrame({"Open": close, "Close": close})
    return {"equity": df, "gold": df.copy()}


def test_the_grid_is_fixed_and_counted():
    g = u.grid()
    assert len(g) == 23 and len({s.name for s in g}) == 23
    assert {s.family for s in g} == set(u.FAMILIES)


# -- no peeking -------------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", u.grid(), ids=lambda s: s.name)
def test_rewriting_the_future_changes_nothing_before_it(strategy):
    """Rewrite every price from day K on at random. Results before K-1 may not move."""
    k = 400
    base = u.run(strategy, BARS)
    rng = np.random.default_rng(99)
    changed = {}
    for key, df in BARS.items():
        df2 = df.copy()
        df2.iloc[k:] = df2.iloc[k:].to_numpy() * rng.uniform(0.5, 1.5, size=df2.iloc[k:].shape)
        changed[key] = df2
    after = u.run(strategy, changed)
    safe = k - 2  # a result also uses the next day's close
    assert [d["pnl"] for d in base[:safe]] == pytest.approx([d["pnl"] for d in after[:safe]])


def _first_month_end_after(i):
    days = BARS["equity"].index
    return next(j for j in range(i, len(days) - 1) if days[j].month != days[j + 1].month)


def _held(strategy, bars):
    p, f = strategy.p, strategy.family
    if f == "trend":
        return u.held_trend(bars, p["n"])
    if f == "dual_momentum":
        return u.held_dual_momentum(bars, p["lookback"], p["mode"])
    if f == "mean_reversion":
        return u.held_mean_reversion(bars, p["entry"], p["exit"])
    return u.held_seasonal(bars, p["kind"], p.get("span", 0), p.get("day", 0))


@pytest.mark.parametrize("k", [400, 450, _first_month_end_after(400), _first_month_end_after(450)])
@pytest.mark.parametrize("factor", [3.0, 0.96, 0.3])
@pytest.mark.parametrize("strategy", u.grid(), ids=lambda s: s.name)
def test_a_position_never_depends_on_the_close_of_the_day_it_is_taken(strategy, factor, k):
    """The position taken at day K's close comes from the signal of day K-1, so K's own close cannot move it."""
    base = _held(strategy, BARS)
    bumped = {key: df.copy() for key, df in BARS.items()}
    for key in bumped:
        bumped[key].iloc[k, bumped[key].columns.get_loc("Close")] *= factor
    after = _held(strategy, bumped)
    assert base.iloc[: k + 1].to_numpy() == pytest.approx(after.iloc[: k + 1].to_numpy())


# -- costs and cash ----------------------------------------------------------------------------


def test_a_delivery_round_trip_costs_a_realistic_fraction_of_a_percent():
    c = u.DEFAULT_COSTS
    round_trip = c.side(100_000, buy=True, intraday=False) + c.side(
        100_000, buy=False, intraday=False
    )
    assert 120 < round_trip < 300  # mostly slippage and brokerage
    intraday = c.side(100_000, buy=True, intraday=True) + c.side(100_000, buy=False, intraday=True)
    assert 120 < intraday < 350


def test_nothing_traded_costs_nothing():
    assert u.DEFAULT_COSTS.side(0, buy=True, intraday=False) == 0.0


def test_cash_earns_the_assumed_yield():
    year = u.cash_only(pd.bdate_range("2020-01-01", periods=252))
    assert sum(d["pnl"] for d in year) == pytest.approx(100_000 * 0.06, rel=0.001)


def test_a_rule_that_trades_often_pays_for_it():
    weekday = u.run(u.strat("seasonal", kind="weekday", day=2), BARS)
    free_costs = u.Costs(
        brokerage=0,
        slippage_pct=0,
        depository=0,
        exchange_pct=0,
        sebi_pct=0,
        stamp_buy_pct=0,
        stt_sell_delivery_pct=0,
    )
    free = u.run(u.strat("seasonal", kind="weekday", day=2), BARS, free_costs)
    assert sum(d["pnl"] for d in free) - sum(d["pnl"] for d in weekday) > 5_000


# -- the rules do what they say ------------------------------------------------------------------


def test_trend_filter_is_flat_before_it_has_data_and_follows_a_steady_rise():
    idx = pd.bdate_range("2020-01-01", periods=300)
    held = u.held_trend(flat_bars(pd.Series(np.linspace(100, 200, 300), index=idx)), 50)
    assert held["equity"].iloc[:50].sum() == 0
    assert held["equity"].iloc[60:].eq(1.0).all()


def test_trend_filter_goes_to_cash_in_a_falling_market():
    idx = pd.bdate_range("2020-01-01", periods=300)
    held = u.held_trend(flat_bars(pd.Series(np.linspace(200, 100, 300), index=idx)), 50)
    assert held["equity"].iloc[60:].sum() == 0


def test_dual_momentum_holds_only_what_rose_and_stays_in_cash_when_nothing_did():
    idx = pd.bdate_range("2020-01-01", periods=400)
    up = pd.Series(np.linspace(100, 160, 400), index=idx)
    down = pd.Series(np.linspace(100, 60, 400), index=idx)
    bars = {
        "equity": pd.DataFrame({"Open": up, "Close": up}),
        "gold": pd.DataFrame({"Open": down, "Close": down}),
    }
    held = u.held_dual_momentum(bars, 63, "best")
    assert held["equity"].iloc[300:].eq(1.0).all() and held["gold"].sum() == 0
    both_down = {"equity": bars["gold"], "gold": bars["gold"]}
    assert u.held_dual_momentum(both_down, 63, "all").iloc[100:].to_numpy().sum() == 0


def test_mean_reversion_buys_a_dip_inside_an_uptrend_and_not_in_a_downtrend():
    idx = pd.bdate_range("2019-01-01", periods=400)
    rise = np.linspace(100, 200, 400)
    rise[300] *= 0.93  # a sharp one-day drop inside an uptrend
    held = u.held_mean_reversion(flat_bars(pd.Series(rise, index=idx)), entry=10, exit=70)["equity"]
    assert held.iloc[301] == 1.0
    down = pd.Series(np.linspace(200, 100, 400), index=idx)
    assert u.held_mean_reversion(flat_bars(down), entry=10, exit=70)["equity"].sum() == 0


def test_the_turn_of_the_month_window_is_a_calendar_fact():
    idx = pd.bdate_range("2021-01-01", periods=80)
    held = u.held_seasonal(flat_bars(pd.Series(100.0, index=idx)), "turn_of_month", span=3)[
        "equity"
    ]
    firsts = held[held.index.to_series().groupby(held.index.to_period("M")).cumcount() < 3]
    assert firsts.eq(1.0).all()
    assert held[(held.index.day > 10) & (held.index.day < 18)].sum() == 0


# -- data and statistics --------------------------------------------------------------------------


def test_a_bad_print_is_dropped_even_when_it_lasts_two_days_but_a_real_crash_is_kept():
    idx = pd.bdate_range("2019-12-10", periods=14)
    close = np.full(14, 129.0)
    close[5:7] = 13.0  # the fund shown at a tenth of its price for two days, as in the real data
    out = u.clean(pd.DataFrame({"Open": close, "Close": close}, index=idx))
    assert len(out) == 12 and out["Close"].min() > 100
    crash = np.array(
        [100, 100, 100, 100, 100, 87, 86, 88, 90, 91, 92, 93, 94, 95.0]
    )  # a real 13 percent day
    assert len(u.clean(pd.DataFrame({"Open": crash, "Close": crash}, index=idx))) == 14


def test_buy_and_hold_pays_one_entry_cost_and_tracks_the_price():
    closes = BARS["equity"]["Close"]
    gross = 100_000 * float(
        (closes.shift(-1) / closes - 1).dropna().sum()
    )  # fixed base, not compounded
    out = u.buy_and_hold(BARS)
    assert sum(d["pnl"] for d in out) == pytest.approx(
        gross - u.DEFAULT_COSTS.side(100_000, buy=True, intraday=False), rel=1e-6
    )


def test_stats_report_return_fall_and_worst_day():
    days = [{"date": f"d{i}", "pnl": p} for i, p in enumerate([1000, -3000, 500, -2000, 4000])]
    s = u.stats(days)
    assert s["total"] == 500.0 and s["worst_day"] == -3000.0 and s["max_drawdown"] == -4500.0
    assert u.stats([])["days"] == 0


# -- the search --------------------------------------------------------------------------------


def test_the_search_reports_trials_baselines_and_a_winner_chosen_without_the_test_period():
    bars = make_bars(days=1400, seed=7)
    found = u.search(bars)
    assert found["trials"] == 23
    seg = found["segments"]
    assert seg["train"][1] < seg["validate"][0] <= seg["validate"][1] < seg["test"][0]
    assert set(found["baselines"]) == {"buy_and_hold", "cash"}
    top = sorted(found["rows"], key=lambda r: r["train_score"], reverse=True)[: u.TOP_ON_TRAIN]
    assert found["winner"] in top
    assert found["winner"]["validate_score"] == max(r["validate_score"] for r in top)


def test_a_rule_that_only_matches_cash_is_not_called_an_edge():
    flat = make_bars(days=1400, seed=3, drift=0.0, vol=0.0001)
    found = u.search(flat)
    assert found["verdict"]["edge_shown"] is False


def test_the_verdict_needs_cash_beaten_in_both_periods_and_buy_and_hold_beaten_or_risk_cut():
    bh = {"cagr": 10.0, "max_drawdown": -20000.0, "worst_day": -5000.0}
    good = {"cagr": 9.0, "max_drawdown": -10000.0, "worst_day": -3000.0}
    assert (
        u.verdict(good, 5000.0, 5000.0, bh)["edge_shown"] is True
    )  # less return, much shallower fall
    assert u.verdict(good, -1.0, 5000.0, bh)["edge_shown"] is False  # lost to cash on validation
    weak = {"cagr": 4.0, "max_drawdown": -19000.0, "worst_day": -3000.0}
    assert u.verdict(weak, 5000.0, 5000.0, bh)["edge_shown"] is False
    wild = {"cagr": 30.0, "max_drawdown": -9000.0, "worst_day": -25000.0}
    v = u.verdict(wild, 5000.0, 5000.0, bh)
    assert v["edge_shown"] is False and not v["within_daily_cap"]


# -- the background job and its endpoint ---------------------------------------------------------------


def test_the_job_writes_a_complete_result_for_the_page(tmp_path):
    import json

    from services.algos import builder_run

    job = tmp_path / "abcdef0123456789"
    job.mkdir()
    bars = make_bars(days=1400, seed=7)
    builder_run.run_universe(
        job, {"kind": "universe", "account": {"capital": 100_000, "max_daily_loss": 20_000}}, bars
    )
    out = json.loads((job / "result.json").read_text())
    assert out["kind"] == "universe" and out["trials"] == 23 and len(out["rules"]) == 23
    assert set(out["baselines"]) == {"buy_and_hold", "cash"}
    assert set(out["winner"]["stats"]) == {"train", "validate", "test"}
    assert out["account"]["within_daily_cap"] in (True, False) and out["account"]["curve"]
    assert any("half Nifty and half gold" in c for c in out["caveats"])
    assert out["verdict"]["headline"]


def test_an_account_of_a_different_size_scales_the_result(tmp_path):
    import json

    from services.algos import builder_run

    bars = make_bars(days=1400, seed=7)
    results = {}
    for capital in (100_000, 300_000):
        job = tmp_path / f"job{capital}"
        job.mkdir()
        builder_run.run_universe(
            job, {"account": {"capital": capital, "max_daily_loss": 60_000}}, bars
        )
        results[capital] = json.loads((job / "result.json").read_text())["account"]
    assert results[300_000]["worst_day"] == pytest.approx(
        3 * results[100_000]["worst_day"], abs=0.5
    )
