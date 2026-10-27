"""Regime scorer: fixed inputs in, label / bias / confidence out."""

import pytest

from services.algos.context import MarketInputs, score_regime


def _inputs(**kw):
    base = {
        "gap_pct": 0.0,
        "sp500_pct": 0.0,
        "nasdaq_pct": 0.0,
        "crude_pct": 0.0,
        "dxy_pct": 0.0,
        "vix": 13.0,
        "vix_change_pct": 0.0,
        "nifty_vs_ma20_pct": 0.0,
    }
    base.update(kw)
    return MarketInputs(**base)


def test_flat_market_is_calm_and_neutral():
    r = score_regime(_inputs())
    assert r.label == "calm"
    assert r.bias == "neutral"
    assert r.confidence == 1.0
    assert r.missing == ()


@pytest.mark.parametrize(
    "kw,label",
    [
        ({"gap_pct": 1.5}, "event"),
        ({"gap_pct": -1.5}, "event"),
        ({"vix": 29.0}, "event"),
        ({"vix": 21.0}, "volatile"),
        ({"vix_change_pct": 9.0}, "volatile"),
        ({"sp500_pct": -2.4}, "volatile"),
        ({"nasdaq_pct": 2.1}, "volatile"),
        ({"gap_pct": 0.6}, "trending"),
        ({"gap_pct": -0.6}, "trending"),
    ],
)
def test_labels(kw, label):
    assert score_regime(_inputs(**kw)).label == label


def test_event_beats_volatile_and_trending():
    assert score_regime(_inputs(gap_pct=1.6, vix=24.0)).label == "event"


def test_bias_follows_gap_and_global_cues():
    up = score_regime(_inputs(gap_pct=0.7, sp500_pct=0.8, nasdaq_pct=1.0))
    down = score_regime(_inputs(gap_pct=-0.7, sp500_pct=-0.8, nasdaq_pct=-1.0))
    assert up.bias == "bullish" and up.score > 0
    assert down.bias == "bearish" and down.score < 0


def test_crude_and_dollar_up_lean_bearish_for_india():
    r = score_regime(_inputs(crude_pct=2.0, dxy_pct=1.0))
    assert r.score < 0


def test_missing_inputs_lower_confidence_and_are_named():
    r = score_regime(_inputs(gap_pct=None, sp500_pct=None))
    assert 0 < r.confidence < 1
    assert "gap_pct" in r.missing and "sp500_pct" in r.missing


def test_missing_vix_is_not_treated_as_zero_volatility():
    r = score_regime(_inputs(vix=None, vix_change_pct=None))
    assert "vix" in r.missing
    assert r.confidence < 1


def test_everything_missing_is_zero_confidence_calm_neutral():
    r = score_regime(MarketInputs())
    assert r.confidence == 0.0
    assert r.bias == "neutral"


def test_reasons_explain_the_label():
    r = score_regime(_inputs(gap_pct=1.5))
    assert any("gap" in s.lower() for s in r.reasons)


def test_missing_data_is_named_in_words_a_trader_reads_not_in_variable_names():
    r = score_regime(MarketInputs(sp500_pct=0.1))
    text = " ".join(r.reasons)
    for internal in ("gap_pct", "vix_change_pct", "nifty_vs_ma20_pct", "sp500_pct"):
        assert internal not in text
    assert "India VIX" in text and "Nifty trend" in text


def test_every_input_has_a_readable_name():
    from services.algos.context import INPUT_LABELS

    assert set(INPUT_LABELS) >= {
        "gap_pct",
        "sp500_pct",
        "nasdaq_pct",
        "crude_pct",
        "dxy_pct",
        "vix",
        "vix_change_pct",
        "nifty_vs_ma20_pct",
    }
    assert all(label and "_" not in label for label in INPUT_LABELS.values())
