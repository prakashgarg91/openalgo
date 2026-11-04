"""What the research study lets the picker say: it predicts the opening gap, not the move after the open."""

import json
from pathlib import Path

import pytest

from services.algos import research_view

LINKAGE = {
    "meta": {"verification": "July 2017 to October 2026"},
    "nodes": [
        {"id": "_GSPC", "label": "S&P 500"},
        {"id": "_IXIC", "label": "Nasdaq"},
        {"id": "DX-Y.NYB", "label": "Dollar index"},
        {"id": "CL_F", "label": "Crude oil"},
    ],
    "links": [
        {"source": "_GSPC", "target": "gap", "status": "verified", "beta_ver": 0.28, "t_ver": 9.8},
        {"source": "_IXIC", "target": "gap", "status": "verified", "beta_ver": 0.22, "t_ver": 11.6},
        {
            "source": "DX-Y.NYB",
            "target": "gap",
            "status": "verified",
            "beta_ver": -0.28,
            "t_ver": -5.6,
        },
        {"source": "CL_F", "target": "gap", "status": "weak", "beta_ver": 0.0142, "t_ver": 1.08},
        {
            "source": "_GSPC",
            "target": "intraday",
            "status": "flipped",
            "beta_ver": -0.01,
            "t_ver": -0.3,
        },
    ],
    "joint_model": [
        {"target": "gap", "r2_full": 0.24, "r2_baseline": -0.0075},
        {"target": "intraday", "r2_full": -0.0267, "r2_baseline": -0.0013},
    ],
}


def test_the_expected_gap_averages_only_the_verified_links_that_have_a_move_today():
    est = research_view.expected_gap(LINKAGE, {"sp500_pct": 1.0, "nasdaq_pct": 1.0, "dxy_pct": 0.5})
    # 0.28*1.0, 0.22*1.0 and -0.28*0.5 averaged; the weak crude link is not used
    assert est["gap_pct"] == pytest.approx((0.28 + 0.22 - 0.14) / 3, abs=1e-6)
    assert {c["label"] for c in est["links"]} == {"S&P 500", "Nasdaq", "Dollar index"}


def test_no_moves_means_no_estimate_not_a_zero():
    est = research_view.expected_gap(
        LINKAGE, {"sp500_pct": None, "nasdaq_pct": None, "dxy_pct": None}
    )
    assert est["gap_pct"] is None and est["links"] == []


def test_the_skill_notes_say_gap_is_predictable_and_the_move_after_the_open_is_not():
    skill = research_view.skill(LINKAGE)
    assert skill["gap"]["usable"] is True
    assert skill["intraday"]["usable"] is False
    assert "after the open" in skill["intraday"]["note"].lower()


def test_a_missing_or_unreadable_study_degrades_to_nothing(tmp_path: Path):
    assert research_view.load(tmp_path / "absent.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert research_view.load(bad) is None
    assert research_view.expected_gap(None, {"sp500_pct": 1.0})["gap_pct"] is None
    assert research_view.skill(None) == {}


def test_the_shipped_study_loads_and_has_a_usable_gap_model():
    study = research_view.load()
    assert study is not None
    assert research_view.skill(study)["gap"]["usable"] is True
    json.dumps(research_view.skill(study))  # serialisable for the page
