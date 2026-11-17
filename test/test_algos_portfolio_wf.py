"""Tests for services/algos/portfolio_wf.py. Pure functions, deterministic, no network."""

from __future__ import annotations

import datetime as dt
import inspect
import random

import services.algos.portfolio_wf as portfolio_wf
from services.algos import portfolio_report
from services.algos.portfolio_select import exit_date_of, month_key
from services.algos.portfolio_wf import run

ALGOS = ["a1", "a2", "a3", "a4"]
CELLS = ["low", "mid", "high"]
PLANTED_CELL = "low"
NUM_MONTHS = 36
NOISE_SD = 3500.0


def _next_weekday(day: dt.date) -> dt.date:
    nxt = day + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return nxt


def build_trades(seed: int, planted: bool = False) -> list[dict]:
    """36 months of weekday trades. Each day has one cell (drawn from CELLS) shared by all four
    algos, and each trade exits on the next weekday after its entry date.

    Every algo trades every day with a Gaussian net (mean 0, sd 3500). With 'planted' set,
    algo a2 gets a mean of +1800 on days in PLANTED_CELL only.
    """
    rng = random.Random(seed)
    trades: list[dict] = []
    for m in range(NUM_MONTHS):
        year = 2023 + m // 12
        month = m % 12 + 1
        day = dt.date(year, month, 1)
        while day.month == month:
            if day.weekday() < 5:
                cell = rng.choice(CELLS)
                exit_day = _next_weekday(day).isoformat()
                for algo in ALGOS:
                    mu = 1800.0 if planted and algo == "a2" and cell == PLANTED_CELL else 0.0
                    net = rng.gauss(mu, NOISE_SD)
                    trades.append(
                        {
                            "date": day.isoformat(),
                            "exit_date": exit_day,
                            "algo": algo,
                            "cell": cell,
                            "net": net,
                        }
                    )
            day += dt.timedelta(days=1)
    return trades


def _eval_months(result: dict) -> list[str]:
    return result["eval_months"]


def test_noise_trap_mean_t_near_zero_and_hindsight_looks_positive():
    t_stats = []
    hindsight_positive = 0
    for seed in range(200):
        result = run(build_trades(seed), CELLS, ALGOS)
        t_stats.append(result["view_b_walk_forward"]["summary"]["t_stat"])
        if result["view_a_hindsight"]["summary"]["net_total"] > 0:
            hindsight_positive += 1
    mean_t = sum(t_stats) / len(t_stats)
    assert abs(mean_t) < 0.25, f"mean walk-forward t over 200 noise seeds was {mean_t:.4f}"
    assert hindsight_positive / 200 > 0.90, (
        f"hindsight net_total was positive on {hindsight_positive} of 200 noise seeds"
    )


def test_planted_edge_is_recovered_by_walk_forward():
    picked = 0
    picked_total = 0
    positive = 0
    for seed in range(50):
        result = run(build_trades(seed, planted=True), CELLS, ALGOS)
        picks = result["view_b_walk_forward"]["picks"]
        for month in _eval_months(result):
            picked_total += 1
            if picks[month][PLANTED_CELL] == "a2":
                picked += 1
        if result["view_b_walk_forward"]["summary"]["net_total"] > 0:
            positive += 1
    assert picked / picked_total >= 0.80, f"a2 picked in {picked} of {picked_total} months"
    assert positive / 50 > 0.80, f"view B net_total positive on {positive} of 50 seeds"


def test_no_look_ahead_from_the_last_month():
    base = build_trades(5)
    before = run(base, CELLS, ALGOS)

    last_month = max(month_key(exit_date_of(t)) for t in base)
    fake_gain = {
        "date": f"{last_month}-28",
        "exit_date": f"{last_month}-28",
        "algo": "a1",
        "cell": PLANTED_CELL,
        "net": 10**9,
    }
    after = run(base + [fake_gain], CELLS, ALGOS)

    earlier = [m for m in _eval_months(before) if m != last_month]
    assert earlier, "need more than one evaluation month to test look-ahead"
    for month in earlier:
        assert (
            before["view_b_walk_forward"]["picks"][month]
            == after["view_b_walk_forward"]["picks"][month]
        )

    # Walk-forward daily series for the earlier months, under each run's own picks.
    earlier_set = set(earlier)

    def earlier_days(trades, result):
        earlier_trades = [t for t in trades if month_key(exit_date_of(t)) in earlier_set]
        return portfolio_report.portfolio_days(
            earlier_trades, result["view_b_walk_forward"]["picks"]
        )

    assert earlier_days(base, before) == earlier_days(base + [fake_gain], after)


def test_module_has_no_io():
    source = inspect.getsource(portfolio_wf)
    for word in ("open(", "requests", "sqlite", "datetime.now", "time.time"):
        assert word not in source, f"portfolio_wf must not mention {word!r}"
