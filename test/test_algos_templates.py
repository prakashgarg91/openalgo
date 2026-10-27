"""Algo templates: regime + capital in, strategy config or a stated skip out."""

import pytest

from blueprints.strategy_module import validate_strategy_config
from services.algos.context import RegimeResult
from services.algos.templates import ALGOS, build


def _regime(label="calm", bias="neutral", confidence=1.0, score=0.0):
    return RegimeResult(
        label=label, bias=bias, score=score, confidence=confidence, reasons=(), missing=()
    )


KW = {"capital": 500_000, "lot_size": 75, "days_to_expiry": 4}


def _legs(plan):
    return {leg["id"]: leg for leg in plan.config["legs"]}


def test_registry_lists_zen_and_mirror_zen():
    assert {"zen", "mirror_zen"} <= set(ALGOS)
    for spec in ALGOS.values():
        assert spec.name and spec.summary and spec.allowed_labels


def test_zen_neutral_is_bull_put_spread_with_published_risk_reward():
    plan = build("zen", _regime("calm", "neutral"), **KW)
    assert plan.action == "trade"
    legs = _legs(plan)
    long_leg = next(leg for leg in legs.values() if leg["position"] == "B")
    short_leg = next(leg for leg in legs.values() if leg["position"] == "S")
    assert long_leg["option_type"] == short_leg["option_type"] == "PE"
    assert short_leg["atm_offset"] == "OTM1" and long_leg["atm_offset"] == "OTM4"
    assert short_leg["sl_pts"] == 30 and short_leg["target_pts"] == 90
    assert short_leg["risk_unit"] == "percent"
    assert plan.config["strategy_type"] == "positional"
    assert plan.config["product"] == "NRML"
    assert plan.config["exit_time"] == "09:45"
    assert plan.config.get("entry_time") is None


def test_zen_bearish_is_bear_call_spread():
    plan = build("zen", _regime("trending", "bearish"), **KW)
    assert {leg["option_type"] for leg in plan.config["legs"]} == {"CE"}


def test_hedge_leg_is_placed_before_the_short_leg():
    plan = build("zen", _regime(), **KW)
    assert [leg["position"] for leg in plan.config["legs"]] == ["B", "S"]


@pytest.mark.parametrize("label", ["event", "volatile"])
def test_zen_skips_unsuitable_regimes_with_a_reason(label):
    plan = build("zen", _regime(label), **KW)
    assert plan.action == "skip" and plan.config is None
    assert label in plan.reason.lower()


def test_low_confidence_skips():
    plan = build("zen", _regime(confidence=0.3), **KW)
    assert plan.action == "skip" and "confidence" in plan.reason.lower()


def test_mirror_zen_is_the_opposite_side_and_needs_a_trend():
    zen = build("zen", _regime("trending", "bullish", 0.9), **KW)
    mirror = build("mirror_zen", _regime("trending", "bullish", 0.9), **KW)
    assert mirror.action == "trade"
    assert {leg["option_type"] for leg in zen.config["legs"]} == {"PE"}
    assert {leg["option_type"] for leg in mirror.config["legs"]} == {"CE"}
    assert build("mirror_zen", _regime("calm"), **KW).action == "skip"
    assert build("mirror_zen", _regime("trending", "bullish", 0.55), **KW).action == "skip"


def test_sizing_caps_worst_case_loss_at_ten_percent_of_capital():
    plan = build("zen", _regime(), capital=500_000, lot_size=75, days_to_expiry=4)
    width = 150
    assert plan.max_loss_inr == plan.lots * 75 * width
    assert plan.max_loss_inr <= 0.10 * 500_000
    assert plan.lots == 4


def test_capital_too_small_for_one_lot_skips():
    plan = build("zen", _regime(), capital=50_000, lot_size=75, days_to_expiry=4)
    assert plan.action == "skip" and "capital" in plan.reason.lower()


def test_lots_never_exceed_the_engine_limit():
    plan = build("zen", _regime(), capital=500_000_000, lot_size=75, days_to_expiry=4)
    assert plan.lots == 50


def test_expiry_within_a_day_rolls_to_next_week():
    near = build("zen", _regime(), capital=500_000, lot_size=75, days_to_expiry=1)
    far = build("zen", _regime(), capital=500_000, lot_size=75, days_to_expiry=4)
    assert {leg["expiry"] for leg in near.config["legs"]} == {"next_week"}
    assert {leg["expiry"] for leg in far.config["legs"]} == {"weekly"}


def test_unknown_algo_raises():
    with pytest.raises(KeyError):
        build("nope", _regime(), **KW)


@pytest.mark.parametrize("algo", ["zen", "mirror_zen"])
@pytest.mark.parametrize("bias", ["bullish", "bearish", "neutral"])
def test_every_emitted_config_passes_the_engine_validator(algo, bias):
    plan = build(algo, _regime("trending", bias, 0.9), **KW)
    assert plan.action == "trade"
    config, error = validate_strategy_config(plan.config)
    assert error is None, error
    assert config["strategy_type"] == "positional"


def test_calm_condor_is_a_four_leg_overnight_condor_on_calm_days_only():
    plan = build("calm_condor", _regime("calm", "neutral", 0.9), **KW)
    assert plan.action == "trade" and plan.side == "iron_condor"
    legs = plan.config["legs"]
    assert [leg["position"] for leg in legs] == ["B", "B", "S", "S"]
    assert {leg["option_type"] for leg in legs if leg["position"] == "S"} == {"CE", "PE"}
    assert all("sl_pts" not in leg for leg in legs if leg["position"] == "B")
    assert plan.config["strategy_type"] == "positional" and plan.config["exit_time"] == "09:45"
    assert plan.max_loss_inr == plan.lots * 75 * 150
    for label in ("trending", "volatile", "event"):
        assert build("calm_condor", _regime(label, "neutral", 0.9), **KW).action == "skip"
    assert build("calm_condor", _regime("calm", "neutral", 0.55), **KW).action == "skip"


def test_calm_condor_passes_the_engine_validator():
    plan = build("calm_condor", _regime("calm", "neutral", 0.9), **KW)
    config, error = validate_strategy_config(plan.config)
    assert error is None, error


def test_coverage_names_the_days_the_platform_stands_aside():
    from services.algos.templates import coverage

    cov = coverage()
    assert "calm_condor" in cov["regimes"]["calm"] and "zen" in cov["regimes"]["calm"]
    assert "mirror_zen" in cov["regimes"]["trending"]
    assert cov["regimes"]["volatile"] == [] and cov["regimes"]["event"] == []
    assert cov["stands_aside_on"] == ["volatile", "event"]
