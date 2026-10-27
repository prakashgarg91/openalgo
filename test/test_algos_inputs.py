"""Input feed: pure parsers and the assembly of MarketInputs."""

import pytest

from services.algos.inputs import (
    assemble_inputs,
    pct_change,
    sma_distance_pct,
    yahoo_change_pct,
)


def test_pct_change():
    assert pct_change(101.0, 100.0) == pytest.approx(1.0)
    assert pct_change(99.0, 100.0) == pytest.approx(-1.0)
    assert pct_change(None, 100.0) is None
    assert pct_change(100.0, 0) is None


def test_sma_distance():
    closes = [100.0] * 19 + [110.0]
    assert round(sma_distance_pct(closes, 20), 3) == round((110 / 100.5 - 1) * 100, 3)
    assert sma_distance_pct([1.0, 2.0], 20) is None


def test_yahoo_change_uses_last_two_closes():
    payload = {
        "chart": {"result": [{"indicators": {"quote": [{"close": [100.0, None, 102.0, 101.0]}]}}]}
    }
    assert round(yahoo_change_pct(payload), 4) == round((101 / 102 - 1) * 100, 4)


def test_yahoo_change_bad_payloads_are_none():
    assert yahoo_change_pct({}) is None
    assert yahoo_change_pct({"chart": {"result": None}}) is None
    assert (
        yahoo_change_pct({"chart": {"result": [{"indicators": {"quote": [{"close": [5.0]}]}}]}})
        is None
    )


def test_assemble_maps_everything():
    m = assemble_inputs(
        nifty={"ltp": 101.0, "prev_close": 100.0},
        vix={"ltp": 15.0, "prev_close": 14.0},
        closes=[100.0] * 20,
        globals_={"sp500": 0.5, "nasdaq": 0.7, "crude": -1.0, "dxy": 0.2},
    )
    assert m.gap_pct == pytest.approx(1.0)
    assert m.vix == 15.0
    assert round(m.vix_change_pct, 3) == round((15 / 14 - 1) * 100, 3)
    assert m.sp500_pct == 0.5 and m.crude_pct == -1.0
    assert m.nifty_vs_ma20_pct is not None


def test_assemble_survives_missing_sources():
    m = assemble_inputs(nifty=None, vix=None, closes=None, globals_={})
    assert m.gap_pct is None and m.vix is None and m.sp500_pct is None


def test_assemble_carries_the_opening_gap_separately_from_the_day_move():
    m = assemble_inputs(
        nifty={"ltp": 100.0, "open": 101.5, "prev_close": 100.0},
        vix=None,
        closes=None,
        globals_={},
    )
    assert m.open_gap_pct == pytest.approx(1.5)
    assert m.gap_pct == pytest.approx(0.0)


def test_assemble_leaves_the_opening_gap_unknown_when_the_quote_has_no_open():
    m = assemble_inputs(
        nifty={"ltp": 100.0, "prev_close": 99.0}, vix=None, closes=None, globals_={}
    )
    assert m.open_gap_pct is None
