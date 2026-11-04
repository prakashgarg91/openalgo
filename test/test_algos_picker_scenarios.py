"""Tests for services/algos/picker_scenarios.py: expiry payoff at multiples of one typical move."""

import math

import pytest

from services.algos.picker import PricedLeg
from services.algos.picker_scenarios import MULTIPLES, scenario_table, sigma_points

SPOT = 23950.0
VIX = 16.0
DTE = 5
LOT = 65


def _leg(kind, strike, side, bid, ask, qty=1):
    return PricedLeg(kind, strike, side, qty, bid, ask)


def test_sigma_points_matches_formula():
    expected = 23950 * 0.16 * math.sqrt(5 / 252)
    assert sigma_points(SPOT, VIX, DTE) == pytest.approx(expected, rel=1e-6)


def test_sigma_points_dte_zero_behaves_like_one():
    assert sigma_points(SPOT, VIX, 0) == pytest.approx(sigma_points(SPOT, VIX, 1), rel=1e-12)


def test_sigma_points_none_for_missing_or_zero_vix():
    assert sigma_points(SPOT, None, DTE) is None
    assert sigma_points(SPOT, 0, DTE) is None
    assert sigma_points(SPOT, -3.0, DTE) is None


def test_long_call_zero_move_and_plus_two():
    legs = [_leg("CE", 23950.0, "B", 99.0, 101.0)]  # price 100
    rows = scenario_table(legs, LOT, SPOT, VIX, DTE, 100.0)
    assert [r["multiple"] for r in rows] == list(MULTIPLES)
    flat = rows[MULTIPLES.index(0)]
    assert flat["pnl"] == -6600.0
    assert flat["label"] == "No move"
    assert flat["nifty"] == round(SPOT, 1)

    sigma = sigma_points(SPOT, VIX, DTE)
    up2 = rows[MULTIPLES.index(2)]
    level = SPOT + 2 * sigma
    assert up2["nifty"] == round(level, 1)
    assert up2["pnl"] == float(round(LOT * (max(level - 23950.0, 0.0) - 100.0) - 100))
    assert up2["label"] == "Up 2 typical moves"
    assert rows[MULTIPLES.index(1)]["label"] == "Up 1 typical move"
    assert rows[MULTIPLES.index(-1)]["label"] == "Down 1 typical move"


def test_short_put_loses_when_down_and_keeps_premium_when_flat():
    legs = [_leg("PE", 23900.0, "S", 99.0, 101.0)]  # sold at 100
    rows = scenario_table(legs, LOT, SPOT, VIX, DTE, 100.0)
    assert rows[MULTIPLES.index(0)]["pnl"] == 6400.0  # 65 * 100 premium less 100 cost
    assert rows[MULTIPLES.index(-1)]["pnl"] < 0
    assert rows[MULTIPLES.index(-2)]["pnl"] < rows[MULTIPLES.index(-1)]["pnl"]


def test_bull_call_spread_is_bounded_at_both_ends():
    legs = [
        _leg("CE", 23950.0, "B", 99.0, 101.0),  # bought at 100
        _leg("CE", 24000.0, "S", 59.0, 61.0),  # sold at 60
    ]
    rows = scenario_table(legs, LOT, SPOT, VIX, DTE, 0.0)
    up2 = rows[MULTIPLES.index(2)]["pnl"]
    up1 = rows[MULTIPLES.index(1)]["pnl"]
    down2 = rows[MULTIPLES.index(-2)]["pnl"]
    # Max profit is (50 - 40 debit) points, max loss is the 40 point debit, both times the lot.
    assert up2 == 650.0
    assert up1 == 650.0
    assert abs(up2 - up1) < 50 * LOT
    assert down2 == -2600.0


def test_call_ratio_spread_sums_both_legs():
    legs = [
        _leg("CE", 23950.0, "B", 99.0, 101.0, qty=1),  # bought at 100
        _leg("CE", 24000.0, "S", 39.0, 41.0, qty=2),  # sold two at 40
    ]
    rows = scenario_table(legs, LOT, SPOT, VIX, DTE, 0.0)
    sigma = sigma_points(SPOT, VIX, DTE)
    for m in MULTIPLES:
        level = SPOT + m * sigma
        expected = LOT * (
            (max(level - 23950.0, 0.0) - 100.0) - 2 * (max(level - 24000.0, 0.0) - 40.0)
        )
        assert rows[MULTIPLES.index(m)]["pnl"] == pytest.approx(round(expected), abs=1)


def test_custom_multiples_and_labels():
    legs = [_leg("CE", 23950.0, "B", 99.0, 101.0)]
    rows = scenario_table(legs, LOT, SPOT, VIX, DTE, 0.0, multiples=(-3, 3))
    assert len(rows) == 2
    assert rows[0]["label"] == "Down 3 typical moves"
    assert rows[1]["label"] == "Up 3 typical moves"
    assert [r["multiple"] for r in rows] == [-3, 3]


def test_returns_none_when_vix_is_none():
    legs = [_leg("CE", 23950.0, "B", 99.0, 101.0)]
    assert scenario_table(legs, LOT, SPOT, None, DTE, 100.0) is None
