"""The pure parts of the picker's past-results script."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "algo_backtest"))
import picker_history as ph  # noqa: E402

from services.algos import picker  # noqa: E402


def test_a_quantity_of_two_becomes_two_legs_in_engine_points():
    legs = ph.expand_legs(picker.template("call_ratio_spread"))
    assert [(g.kind, g.offset, g.side) for g in legs] == [
        ("CE", 0, 1),
        ("CE", 100, -1),
        ("CE", 100, -1),
    ]


def test_a_structure_wider_than_the_engine_is_not_expressible():
    wide = picker.Template(
        "x", "x", tuple(picker.Leg("CE", i, "B") for i in range(5)), "any", "flat", (0, 1), (0, 1)
    )
    assert ph.expand_legs(wide) is None


def test_short_calls_beyond_the_long_ones_are_flagged_as_unbounded():
    assert ph.undefined_loss(picker.template("short_straddle")) is True
    assert ph.undefined_loss(picker.template("bear_call_spread")) is False


def test_the_summary_keeps_the_spread_the_buckets_and_the_recent_third_apart():
    nets = [100.0] * 6 + [-300.0] * 3
    vix = [12.0] * 6 + [16.0] * 3
    entries = [pd.Timestamp("2024-01-01") + pd.Timedelta(days=7 * i) for i in range(9)]
    s = ph.summarize(nets, vix, entries)
    assert (
        s["trades"] == 9
        and s["worst"] == -300.0
        and s["win_rate"] == pytest.approx(6 / 9, abs=1e-3)
    )
    assert s["by_vix"]["low"]["trades"] == 6 and s["by_vix"]["mid"]["mean"] == -300.0
    assert s["recent_mean"] == -300.0 and s["older_mean"] == 100.0


def test_no_priced_week_is_not_replayable():
    assert ph.summarize([], [], [])["replayable"] is False
