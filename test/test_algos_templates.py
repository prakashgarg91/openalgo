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


def test_overnight_algos_wait_out_the_days_before_expiry_instead_of_rolling():
    for algo, regime in (
        ("zen", _regime()),
        ("calm_condor", _regime("calm", "neutral", 0.9)),
        ("mirror_zen", _regime("trending", "bullish", 0.9)),
    ):
        for dte in (0, 1):
            plan = build(algo, regime, capital=500_000, lot_size=75, days_to_expiry=dte)
            assert plan.action == "skip" and "Expiry is today or tomorrow" in plan.reason
        far = build(algo, regime, capital=500_000, lot_size=75, days_to_expiry=2)
        assert far.action == "trade"
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


def test_every_algo_carries_evidence_and_none_is_called_tested_without_a_profit():
    # Real option prices (2023 to 2026) showed no net edge for any of them.
    assert all(spec.evidence for spec in ALGOS.values())
    assert all(spec.status == "experimental" for spec in ALGOS.values())
    for algo in ("zen", "mirror_zen", "calm_condor"):
        assert "real NSE option prices" in ALGOS[algo].evidence
        assert "lost money" in ALGOS[algo].evidence


def _gap(pct, **kw):
    from services.algos.context import MarketInputs

    return MarketInputs(open_gap_pct=pct, **kw)


MORNING = {"capital": 500_000, "lot_size": 75, "days_to_expiry": 3}


def test_morning_gap_fades_a_large_gap_up_with_a_bear_call_spread():
    plan = build("morning_gap", _regime("trending", "bullish", 0.9), inputs=_gap(0.9), **MORNING)
    assert plan.action == "trade" and plan.side == "bear_call"
    assert {leg["option_type"] for leg in plan.config["legs"]} == {"CE"}


def test_morning_gap_fades_a_large_gap_down_with_a_bull_put_spread():
    plan = build("morning_gap", _regime("trending", "bearish", 0.9), inputs=_gap(-0.9), **MORNING)
    assert plan.action == "trade" and plan.side == "bull_put"
    assert {leg["option_type"] for leg in plan.config["legs"]} == {"PE"}


def test_morning_gap_is_an_intraday_mis_spread_closed_before_the_session_ends():
    plan = build("morning_gap", _regime("trending", "bullish", 0.9), inputs=_gap(0.9), **MORNING)
    cfg = plan.config
    assert cfg["strategy_type"] == "intraday" and cfg["product"] == "MIS"
    assert cfg["entry_time"] == "09:25" and cfg["exit_time"] == "15:15"
    assert [leg["position"] for leg in cfg["legs"]] == ["B", "S"]
    assert {leg["expiry"] for leg in cfg["legs"]} == {"weekly"}


def test_morning_gap_config_passes_the_engine_validator():
    plan = build("morning_gap", _regime("trending", "bullish", 0.9), inputs=_gap(0.9), **MORNING)
    config, error = validate_strategy_config(plan.config)
    assert error is None, error


@pytest.mark.parametrize("pct", [0.0, 0.3, -0.5, 0.74])
def test_morning_gap_stands_aside_on_a_small_gap(pct):
    plan = build("morning_gap", _regime("calm", "neutral", 0.9), inputs=_gap(pct), **MORNING)
    assert plan.action == "skip" and "too small" in plan.reason


def test_morning_gap_needs_the_gap_to_be_known():
    for inputs in (None, _gap(None)):
        plan = build("morning_gap", _regime("calm", "neutral", 0.9), inputs=inputs, **MORNING)
        assert plan.action == "skip" and "not available" in plan.reason


def test_morning_gap_skips_expiry_day_and_event_and_volatile_days():
    base = {"capital": 500_000, "lot_size": 75}
    expiry = build(
        "morning_gap",
        _regime("trending", "bullish", 0.9),
        inputs=_gap(0.9),
        days_to_expiry=0,
        **base,
    )
    assert expiry.action == "skip" and "expiry day" in expiry.reason
    for label in ("event", "volatile"):
        plan = build(
            "morning_gap",
            _regime(label, "bullish", 0.9),
            inputs=_gap(0.9),
            days_to_expiry=3,
            **base,
        )
        assert plan.action == "skip"


def test_other_algos_ignore_the_inputs_argument():
    a = build("zen", _regime(), **KW)
    b = build("zen", _regime(), inputs=_gap(5.0), **KW)
    assert a.config == b.config


def test_morning_gap_is_experimental_and_checks_at_0925():
    spec = ALGOS["morning_gap"]
    assert spec.status == "experimental" and spec.entry_time == "09:25" and not spec.overnight
    assert "lost money" in spec.evidence
    assert all(a.entry_time == "15:05" for a in ALGOS.values() if a.overnight)
