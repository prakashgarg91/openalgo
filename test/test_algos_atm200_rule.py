"""Tests for services/algos/atm200_rule.py: the frozen ATM 200-point call credit spread rule.

Pure tests. No network, no files, no clock.
"""

from __future__ import annotations

import math

import pytest

from services.algos import atm200_rule as rule
from services.algos.atm200_rule import (
    REASON_CREDIT_SMALL,
    REASON_PRICE_MISSING,
    REASON_VIX_HIGH,
    atm_strike,
    exit_decision,
    ledger_should_stop,
    plan_entry,
    pnl_rupees,
    spread_value,
)

NAN = float("nan")


def test_every_constant_has_the_frozen_value():
    assert rule.WIDTH == 200
    assert rule.TARGET == 0.31
    assert rule.STOP == 2.5
    assert rule.VIX_SKIP_AT == 20.0
    assert rule.MIN_CREDIT_POINTS == 5.0
    assert rule.MAX_DAYS_TO_EXPIRY == 6
    assert rule.ENTRY_TIME == "10:15"
    assert rule.LAST_EXIT_TIME == "15:00"
    assert rule.LOT == 65
    assert rule.MAX_LOSS_RUPEES_LEDGER_STOP == 20000


@pytest.mark.parametrize(
    ("spot", "expected"),
    [
        (25024, 25000),
        (25025, 25000),
        (25075, 25100),
        (25049.9, 25050),
        (25000, 25000),
        (25074.9, 25050),
        (25075, 25100),
    ],
)
def test_atm_strike_rounds_to_nearest_50_like_the_replay(spot, expected):
    assert atm_strike(spot) == expected
    assert isinstance(atm_strike(spot), int)


@pytest.mark.parametrize(
    ("vix", "skipped"), [(19.99, False), (20.0, True), (None, False), (NAN, False)]
)
def test_vix_gate(vix, skipped):
    plan = plan_entry(25000, vix, 30.0, 10.0)
    if skipped:
        assert plan.skipped_reason == REASON_VIX_HIGH
    else:
        assert plan.skipped_reason is None


def test_vix_reason_text_is_plain():
    assert REASON_VIX_HIGH == "The previous India VIX close was 20 or higher."


@pytest.mark.parametrize(("credit", "skipped"), [(5.0, True), (5.01, False)])
def test_credit_floor(credit, skipped):
    plan = plan_entry(25000, 15.0, 10.0 + credit, 10.0)
    if skipped:
        assert plan.skipped_reason == REASON_CREDIT_SMALL
    else:
        assert plan.skipped_reason is None
        assert plan.credit_points == pytest.approx(credit)


def test_plan_entry_strikes_and_credit_on_trade():
    plan = plan_entry(25024, 14.0, 42.5, 12.5)
    assert plan.sold_strike == 25000
    assert plan.bought_strike == 25200
    assert plan.credit_points == pytest.approx(30.0)
    assert plan.skipped_reason is None


def test_plan_entry_missing_price_or_spot_is_skipped():
    for args in [
        (25000, 15.0, None, 10.0),
        (25000, 15.0, 30.0, NAN),
        (None, 15.0, 30.0, 10.0),
    ]:
        plan = plan_entry(*args)
        assert plan.skipped_reason == REASON_PRICE_MISSING
        assert plan.credit_points is None


def test_spread_value_is_sold_minus_bought():
    assert spread_value(30.0, 12.5) == pytest.approx(17.5)


def test_target_fires_at_boundary_and_is_checked_first():
    credit = 24.0
    assert exit_decision(credit, target_value(credit), False) == "target"
    assert exit_decision(credit, credit * rule.TARGET - 0.5, False) == "target"
    # On the last bar a target still wins over the time exit.
    assert exit_decision(credit, target_value(credit), True) == "target"


def test_stop_fires_at_boundary():
    credit = 24.0
    assert exit_decision(credit, stop_value(credit), False) == "stop"
    assert exit_decision(credit, credit * rule.STOP + 1, False) == "stop"


def test_just_inside_both_bands_holds():
    credit = 24.0
    just_above_target = math.nextafter(target_value(credit), math.inf)
    just_below_stop = math.nextafter(stop_value(credit), -math.inf)
    assert exit_decision(credit, just_above_target, False) is None
    assert exit_decision(credit, just_below_stop, False) is None


def test_time_exit_only_on_last_bar():
    credit = 24.0
    assert exit_decision(credit, 15.0, False) is None
    assert exit_decision(credit, 15.0, True) == "time"


def test_pnl_win_and_loss_with_lot_65():
    assert pnl_rupees(24, 7.44) == pytest.approx((24 - 7.44) * 65)
    assert pnl_rupees(24, 7.44) == pytest.approx(1076.4)
    assert pnl_rupees(24, 50) == pytest.approx((24 - 50) * 65)
    assert pnl_rupees(24, 50) == pytest.approx(-1690.0)


def test_pnl_default_lot_is_the_lot_constant():
    assert pnl_rupees(10, 4, lot=7) == pytest.approx(42.0)
    assert pnl_rupees(10, 4) == pytest.approx(6 * rule.LOT)


def test_ledger_stop_boundaries():
    assert ledger_should_stop(-19999) is False
    assert ledger_should_stop(-20000) is True
    assert ledger_should_stop(-25000) is True
    assert ledger_should_stop(0) is False


def target_value(credit: float) -> float:
    return rule.TARGET * credit


def stop_value(credit: float) -> float:
    return rule.STOP * credit
