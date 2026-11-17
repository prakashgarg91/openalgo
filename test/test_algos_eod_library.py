"""Tests for services/algos/eod_library.py and scripts/algo_backtest/eod_library_run.py.

Synthetic rows only. No test reads the NSE option table or any real price. The run script is tested
only for its guard, which must refuse in every case here.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import inspect
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from services.algos import eod_library, portfolio_select, portfolio_wf
from services.algos.eod_library import (
    ALGOS,
    LIBRARY,
    TRADEABLE_CELLS,
    build_trades,
    build_trades_counted,
    cell_for,
    clamp_spread_value,
    leg_price_exit,
    legs_for,
    settle_value,
    trade_net,
)
from services.algos.portfolio_select import exit_date_of, trailing_window

ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = ROOT / "scripts" / "algo_backtest" / "eod_library_run.py"
REG_DOC = "docs/algos/eod-library-registration-DRAFT-2026-11-17.md"
ATM = 22000
LOT = 75
ENTRY_DAY = "2025-03-03"  # before the April 2026 STT change, so the lower STT rate applies
EXIT_DAY = "2025-03-04"
NUM_MONTHS = 36
NOISE_SD_POINTS = 3500.0 / LOT  # 3,500 rupees a trade, as in the harness's own noise test
PLANTED_POINTS = 1800.0 / LOT  # a planted edge of 1,800 rupees a trade on algo A1, low cell


# ---------------------------------------------------------------------------------------------
# Leg construction
# ---------------------------------------------------------------------------------------------


def test_legs_for_all_five_algos_at_the_money():
    assert legs_for("A1", 22000) == [("CE", 22000, "SELL"), ("CE", 22200, "BUY")]
    assert legs_for("A2", 22000) == [("PE", 22000, "SELL"), ("PE", 21800, "BUY")]
    assert legs_for("A3", 22000) == [
        ("CE", 22200, "SELL"),
        ("CE", 22400, "BUY"),
        ("PE", 21800, "SELL"),
        ("PE", 21600, "BUY"),
    ]
    assert legs_for("A4", 22000) == [("CE", 22000, "BUY"), ("CE", 22200, "SELL")]
    assert legs_for("A5", 22000) == [("PE", 22000, "BUY"), ("PE", 21800, "SELL")]
    assert ALGOS == ("A1", "A2", "A3", "A4", "A5")
    assert len(LIBRARY["A3"]) == 4


def test_legs_for_unknown_algo_is_refused():
    with pytest.raises(ValueError):
        legs_for("A6", 22000)


def test_legs_follow_the_atm_strike():
    assert legs_for("A1", 21950)[1][1] == 22150


def test_only_the_low_cell_is_tradeable():
    assert TRADEABLE_CELLS == ("low",)


# ---------------------------------------------------------------------------------------------
# Settlement, clamp and expiry-day exit valuation
# ---------------------------------------------------------------------------------------------


def test_settle_value_is_intrinsic_on_each_side():
    assert settle_value("CE", 22000, 22150) == 150
    assert settle_value("CE", 22000, 21900) == 0
    assert settle_value("PE", 22000, 21900) == 100
    assert settle_value("PE", 22000, 22150) == 0
    with pytest.raises(ValueError):
        settle_value("FUT", 22000, 22150)


def test_clamp_keeps_a_spread_between_zero_and_its_width():
    assert clamp_spread_value(250, 200) == 200
    assert clamp_spread_value(-5, 200) == 0
    assert clamp_spread_value(120, 200) == 120


def test_expiry_day_exit_uses_settlement_not_the_close():
    expiry = pd.Timestamp("2025-03-04")
    # The option closed at 50 on expiry day, but the index settled at 22150, so the call is worth 150.
    assert leg_price_exit("CE", 22000, 50.0, 22150.0, expiry, expiry) == 150.0


def test_normal_exit_uses_the_close_on_the_exit_day():
    assert (
        leg_price_exit(
            "CE", 22000, 50.0, 22150.0, pd.Timestamp("2025-03-06"), pd.Timestamp("2025-03-04")
        )
        == 50.0
    )


def test_expiry_day_exit_without_a_settlement_is_missing():
    expiry = pd.Timestamp("2025-03-04")
    assert leg_price_exit("CE", 22000, 50.0, None, expiry, expiry) is None
    assert leg_price_exit("CE", 22000, 50.0, float("nan"), expiry, expiry) is None


def test_missing_close_on_a_normal_exit_is_missing():
    assert (
        leg_price_exit(
            "PE", 22000, None, 22150.0, pd.Timestamp("2025-03-06"), pd.Timestamp("2025-03-04")
        )
        is None
    )


# ---------------------------------------------------------------------------------------------
# trade_net, hand-computed
#
# Realistic costs per leg, from services/algos/costs.py: brokerage 20 a leg (two orders, so 40), STT
# 0.1 percent of the premium sold (entry for a sold leg, exit for a bought one), exchange 0.0345
# percent and SEBI 0.0001 percent of turnover, GST 18 percent of brokerage plus exchange plus SEBI,
# stamp 0.003 percent of the bought premium, slippage 0.15 points a side (so 0.3 points, 22.5 rupees
# a 75-lot leg). Sum over a leg with entry e and exit x at lot 75:
#   sale part  = 0.075 * e (sold leg) or 0.075 * x (bought leg)
#   the rest   = 69.7 + 0.00040828 * (e + x) * 75 + stamp, stamp = 0.00225 * x (sold) or * e (bought)
# ---------------------------------------------------------------------------------------------


def test_trade_net_a1_hand_computed_with_four_costs():
    # Sell ATM call 120 -> 90; buy +200 call 40 -> 25. Gross (+30 sold, -15 bought) = 15 points.
    net = trade_net("A1", ATM, [120.0, 40.0], [90.0, 25.0], LOT, ENTRY_DAY, EXIT_DAY)
    # Leg costs by hand: sold leg 85.33291, bought leg 73.65537. Gross 15 * 75 = 1125.
    assert net == pytest.approx(1125.0 - 158.98828, abs=1e-3)
    doubled = trade_net(
        "A1", ATM, [120.0, 40.0], [90.0, 25.0], LOT, ENTRY_DAY, EXIT_DAY, doubled=True
    )
    assert doubled == pytest.approx(1125.0 - 2 * 158.98828, abs=1e-3)


def test_trade_net_a3_hand_computed_with_eight_costs():
    # Four legs: sold 22200 call 60 -> 45, bought 22400 call 20 -> 12, sold 21800 put 55 -> 40,
    # bought 21600 put 18 -> 10. Gross 15 - 8 + 15 - 8 = 14 points, so 1050 rupees.
    entry = [60.0, 20.0, 55.0, 18.0]
    exit_ = [45.0, 12.0, 40.0, 10.0]
    # Leg costs by hand: 77.51646, 71.62487, 76.82400, 71.34789. Sum 297.31321.
    net = trade_net("A3", ATM, entry, exit_, LOT, ENTRY_DAY, EXIT_DAY)
    assert net == pytest.approx(1050.0 - 297.31321, abs=1e-3)
    doubled = trade_net("A3", ATM, entry, exit_, LOT, ENTRY_DAY, EXIT_DAY, doubled=True)
    assert doubled == pytest.approx(1050.0 - 2 * 297.31321, abs=1e-3)


def test_trade_net_refuses_a_missing_price_and_a_wrong_leg_count():
    with pytest.raises(ValueError):
        trade_net("A1", ATM, [120.0, None], [90.0, 25.0], LOT, ENTRY_DAY, EXIT_DAY)
    with pytest.raises(ValueError):
        trade_net("A1", ATM, [120.0], [90.0], LOT, ENTRY_DAY, EXIT_DAY)


# ---------------------------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "group, expected",
    [
        (1, "low"),
        (2, "low"),
        (3, "mid"),
        (4, "high"),
        (5, "high"),
        (None, "unlabelled"),
        (9, "unlabelled"),
    ],
)
def test_cell_for_maps_regime_groups(group, expected):
    assert cell_for(group, False, False) == expected


def test_cell_for_event_days_win_over_the_group():
    assert cell_for(1, True, False) == "event"
    assert cell_for(3, False, True) == "event"
    assert cell_for(5, True, True) == "event"


# ---------------------------------------------------------------------------------------------
# build_trades counts and drops
# ---------------------------------------------------------------------------------------------


def _full_legs(entry: float = 100.0, exit_: float = 110.0) -> dict:
    """Every algo priced: each leg enters at entry and exits at exit_."""
    return {
        algo: {"entry": [entry] * len(LIBRARY[algo]), "exit": [exit_] * len(LIBRARY[algo])}
        for algo in ALGOS
    }


def _row(**over) -> dict:
    row = {
        "entry_date": ENTRY_DAY,
        "exit_date": EXIT_DAY,
        "group": 1,
        "entry_is_event": False,
        "exit_is_event": False,
        "atm": ATM,
        "lot": LOT,
        "usable": True,
        "legs": _full_legs(),
    }
    row.update(over)
    return row


def test_build_trades_keeps_every_algo_on_a_usable_day():
    trades, counts = build_trades_counted([_row()])
    assert counts == {
        "candidates": 5,
        "kept": 5,
        "dropped_unusable_day": 0,
        "dropped_unusable_leg": 0,
    }
    assert {t["algo"] for t in trades} == set(ALGOS)
    t = next(t for t in trades if t["algo"] == "A1")
    assert t["date"] == ENTRY_DAY and t["exit_date"] == EXIT_DAY and t["cell"] == "low"
    assert set(t) == {"date", "exit_date", "algo", "cell", "net"}


def test_build_trades_drops_and_counts_unusable_legs_and_days():
    legs_with_gap = _full_legs()
    legs_with_gap["A3"]["exit"][2] = None  # one leg of the condor has no exit price
    rows = [
        _row(legs=legs_with_gap),  # A3 dropped as an unusable leg; four algos kept
        _row(usable=False),  # all five dropped as an unusable day
        _row(group=3),  # mid cell: still built and labelled, the harness never trades it
    ]
    trades, counts = build_trades_counted(rows)
    assert counts["candidates"] == 15
    assert counts["dropped_unusable_leg"] == 1
    assert counts["dropped_unusable_day"] == 5
    assert counts["kept"] == 9
    assert len(trades) == 9
    assert not any(t["algo"] == "A3" and t["cell"] == "low" for t in trades)
    assert sum(1 for t in trades if t["cell"] == "mid") == 5


def test_build_trades_doubled_costs_are_the_doubled_nets():
    single = build_trades([_row()])
    double = build_trades([_row()], doubled=True)
    gross = {t["algo"]: t["net"] for t in single}
    for t in double:
        assert t["net"] < gross[t["algo"]]


def test_build_trades_drops_a_row_without_an_atm_or_lot():
    trades, counts = build_trades_counted([_row(atm=None), _row(lot=None)])
    assert trades == []
    assert counts["dropped_unusable_day"] == 10


# ---------------------------------------------------------------------------------------------
# Harness end to end on synthetic day rows
# ---------------------------------------------------------------------------------------------


def _weekdays() -> list[dt.date]:
    day = dt.date(2023, 1, 2)
    out = []
    for _ in range(NUM_MONTHS * 22):
        if day.weekday() < 5:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def _next_weekday(day: dt.date) -> dt.date:
    nxt = day + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return nxt


def _synthetic_rows(seed: int, planted: bool = False, groups: tuple[int, ...] = (1, 2, 3, 4, 5)):
    """Day rows where every algo has zero expected net before any planted edge.

    The gross sits on the first leg: its exit is entry plus the move times that leg's sign, so the
    rupee gross is the move itself (Gaussian, sd 3,500 rupees a trade). The move is shifted by that
    trade's own cost in points, so the expected net is zero: a pure-noise library with no edge. A
    zero-mean gross without the shift gives a walk-forward t near -0.8 from costs alone, a real drag
    that is not the noise trap this test is for. Other legs exit where they entered.
    With 'planted', A1 gets +1,800 rupees a trade on the days in group 1 or 2 (the low cell).
    """
    rng = random.Random(seed)
    rows = []
    for day in _weekdays():
        group = rng.choice(groups)
        entry_day, exit_day = day.isoformat(), _next_weekday(day).isoformat()
        legs = {}
        for algo in ALGOS:
            first_sign = 1 if LIBRARY[algo][0][2] == "BUY" else -1
            entry = [300.0] * len(LIBRARY[algo])

            def exit_with(move: float, entry=entry, first_sign=first_sign) -> list[float]:
                ex = list(entry)
                ex[0] = 300.0 + first_sign * move
                return ex

            cost_points = (
                -trade_net(algo, ATM, entry, exit_with(0.0), LOT, entry_day, exit_day) / LOT
            )
            move = rng.gauss(0.0, NOISE_SD_POINTS) + cost_points
            if planted and algo == "A1" and group in (1, 2):
                move += PLANTED_POINTS
            legs[algo] = {"entry": entry, "exit": exit_with(move)}
        rows.append(
            {
                "entry_date": entry_day,
                "exit_date": exit_day,
                "group": group,
                "entry_is_event": False,
                "exit_is_event": False,
                "atm": ATM,
                "lot": LOT,
                "usable": True,
                "legs": legs,
            }
        )
    return rows


CELLS = list(TRADEABLE_CELLS)


def test_noise_walk_forward_t_is_near_zero_and_hindsight_looks_positive():
    t_stats = []
    hindsight_positive = 0
    seeds = 100
    for seed in range(seeds):
        trades = build_trades(_synthetic_rows(seed))
        result = portfolio_wf.run(trades, CELLS, list(ALGOS), first_month="2022-04")
        t_stats.append(result["view_b_walk_forward"]["summary"]["t_stat"])
        if result["view_a_hindsight"]["summary"]["net_total"] > 0:
            hindsight_positive += 1
    mean_t = sum(t_stats) / seeds
    assert abs(mean_t) < 0.25, f"mean walk-forward t over {seeds} noise seeds was {mean_t:.4f}"
    assert hindsight_positive > seeds / 2, (
        f"hindsight net_total was positive on {hindsight_positive} of {seeds} noise seeds"
    )


def test_planted_edge_in_a1_low_cell_is_recovered_by_walk_forward():
    picked = 0
    picked_total = 0
    positive = 0
    seeds = 30
    for seed in range(seeds):
        trades = build_trades(_synthetic_rows(seed, planted=True))
        result = portfolio_wf.run(trades, CELLS, list(ALGOS), first_month="2022-04")
        view = result["view_b_walk_forward"]
        for month in result["eval_months"]:
            picked_total += 1
            if view["picks"][month]["low"] == "A1":
                picked += 1
        if view["summary"]["net_total"] > 0:
            positive += 1
    assert picked / picked_total >= 0.80, f"A1 picked in {picked} of {picked_total} low-cell months"
    assert positive / seeds > 0.80, f"view B net_total positive on {positive} of {seeds} seeds"


def test_mid_and_high_cells_never_produce_a_trade():
    rows = _synthetic_rows(7, planted=True, groups=(3, 4, 5))
    trades = build_trades(rows)
    assert trades and {t["cell"] for t in trades} == {"mid", "high"}
    result = portfolio_wf.run(trades, CELLS, list(ALGOS), first_month="2022-04")
    assert result["view_b_walk_forward"]["summary"]["n_trades_days"] == 0
    assert result["view_b_walk_forward"]["summary"]["net_total"] == 0
    assert result["view_a_hindsight"]["summary"]["n_trades_days"] == 0
    for month_picks in result["view_b_walk_forward"]["picks"].values():
        assert set(month_picks) == {"low"}
    assert set(result["view_a_hindsight"]["picks"]) == {"low"}


def test_trades_are_dated_by_exit_day_across_a_month_end():
    rows = [
        _row(
            entry_date="2025-01-31",
            exit_date="2025-02-03",
            legs={"A1": {"entry": [120.0, 40.0], "exit": [90.0, 25.0]}},
        )
    ]
    trades = build_trades(rows)
    a1 = next(t for t in trades if t["algo"] == "A1")
    assert a1["date"] == "2025-01-31" and a1["exit_date"] == "2025-02-03"
    assert exit_date_of(a1) == "2025-02-03"
    # The result is known on Monday 3 February, so it is in February's history, not January's.
    assert trailing_window([a1], "2025-02") == []
    assert trailing_window([a1], "2025-03") == [a1]
    assert portfolio_select.month_key(exit_date_of(a1)) == "2025-02"


def test_the_expiry_day_settlement_feeds_a_trade_net():
    # A1 sells the ATM call and buys +200. Expiry-day exit at settlement 22150 (not the close):
    # sold call worth 150 at expiry, bought 200 call worth 0.
    expiry = pd.Timestamp("2025-03-04")
    sold_exit = leg_price_exit("CE", 22000, 50.0, 22150.0, expiry, expiry)
    bought_exit = leg_price_exit("CE", 22200, 5.0, 22150.0, expiry, expiry)
    assert (sold_exit, bought_exit) == (150.0, 0.0)
    net = trade_net("A1", ATM, [200.0, 40.0], [sold_exit, bought_exit], LOT, ENTRY_DAY, EXIT_DAY)
    gross = (200.0 - 150.0) + (0.0 - 40.0)
    assert net < gross * LOT  # costs are taken off the gross


# ---------------------------------------------------------------------------------------------
# No I/O in the pure module
# ---------------------------------------------------------------------------------------------


def test_eod_library_module_has_no_io():
    source = inspect.getsource(eod_library)
    for word in (
        "open(",
        "import requests",
        "import sqlite",
        "datetime.now",
        "time.time",
        "import logging",
        "print(",
    ):
        assert word not in source, f"eod_library must not mention {word!r}"


# ---------------------------------------------------------------------------------------------
# The run script's guard
# ---------------------------------------------------------------------------------------------


def _load_run_script():
    spec = importlib.util.spec_from_file_location("eod_library_run", RUN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(env_value: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "EOD_LIBRARY_FROZEN"}
    if env_value is not None:
        env["EOD_LIBRARY_FROZEN"] = env_value
    return subprocess.run(
        [sys.executable, str(RUN_SCRIPT), str(ROOT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=120,
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git is needed for the guard")
def test_guard_refuses_without_the_environment_variable():
    done = _run(None)
    assert done.returncode == 2
    assert "This run is blocked until the registration is frozen." in done.stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="git is needed for the guard")
def test_guard_refuses_a_sha_that_is_not_an_ancestor():
    done = _run("0123456789abcdef0123456789abcdef01234567")
    assert done.returncode == 2
    assert "This run is blocked until the registration is frozen." in done.stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="git is needed for the guard")
def test_guard_refuses_a_non_sha_value():
    done = _run("main; rm -rf /")
    assert done.returncode == 2
    assert "This run is blocked until the registration is frozen." in done.stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="git is needed for the guard")
def test_guard_refuses_an_ancestor_that_is_not_frozen():
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    if not head:
        pytest.skip("not a git checkout")
    doc = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{head}:{REG_DOC}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    if "STATUS: FROZEN" in doc:
        pytest.skip("HEAD is already the frozen commit")
    module = _load_run_script()
    ok, why = module.frozen_check(head, ROOT)
    assert not ok
    assert "STATUS: FROZEN" in why
    done = _run(head)
    assert done.returncode == 2
    assert "This run is blocked until the registration is frozen." in done.stdout
