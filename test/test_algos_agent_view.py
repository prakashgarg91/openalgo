"""The read-only views the agent and the page use: they report, and they write nothing."""

import json
from datetime import datetime

import pytest

from services.algos import agent_view as av
from services.algos import registry as reg

JAN = datetime(2027, 1, 4, 10, 0)
NOV = datetime(2026, 11, 2, 10, 0)


def draft(**over):
    base = {
        "name": "Vol scaled equity gold", "idea": "Hold less equity when forecast volatility is high.",
        "instrument": "NIFTYBEES and GOLDBEES", "entry": "At each month-end close set the weights.",
        "exit": "Rebalance at the next month-end.", "size": "Rs 1,00,000, whole shares",
        "costs": "universe.py schedule and doubled", "benchmark": "A same-exposure hold",
        "why_it_might_work": "Volatility is predictable.", "how_it_fails": "Costs eat it.",
        "data_seen": "All ETF history", "data_unseen": "Forward only", "end_rule": "24 decisions",
        "kill_rule": "Minus Rs 5,000", "gates": ["positive net at both cost levels"],
        "params": {"target_vol": 0.1},
    }  # fmt: skip
    return {**base, **over}


def test_the_register_view_reports_the_count_the_bar_and_the_next_free_month(tmp_path):
    out = av.register_status(tmp_path, NOV)
    assert (
        out["trial_count"] == 319
        and out["next_free_month"] == "2027-01"
        and out["registrations"] == []
    )
    reg.register(draft(), tmp_path, JAN)
    out = av.register_status(tmp_path, JAN)
    assert out["trial_count"] == 320 and out["registrations"][0]["status"] == "registered"
    assert out["registrations"][0]["intact"] is True


def test_validating_a_draft_names_what_stops_it_and_writes_nothing(tmp_path):
    out = av.validate_draft(draft(how_it_fails=""), tmp_path, JAN)
    assert out["ready_to_register"] is False and any("how it fails" in p for p in out["problems"])
    assert out["written"] is False and not list(tmp_path.iterdir())
    used = av.validate_draft(draft(), tmp_path, NOV)
    assert any("C1 month-end ETF window" in p and "2027-01" in p for p in used["problems"])
    assert av.validate_draft(draft(), tmp_path, JAN)["ready_to_register"] is True
    assert not list(tmp_path.iterdir())  # still nothing written


def test_a_draft_that_restates_a_registered_idea_is_flagged(tmp_path):
    reg.register(draft(), tmp_path, JAN)
    again = draft(
        name="Volatility scaled equity gold",
        idea="Hold less equity when forecast volatility is high.",
    )
    out = av.validate_draft(again, tmp_path, datetime(2027, 2, 1))
    assert any("restates an idea already registered" in p for p in out["problems"])


def test_what_was_tried_before_is_searched_in_the_register_and_the_results_pages(tmp_path):
    (tmp_path / "TRIAL_REGISTER.md").write_text(
        "| Daily real-price grid | 48 | 33 of 48 lost |\n", encoding="utf-8"
    )
    (tmp_path / "x-results.md").write_text(
        "The calendar window lost money.\nunrelated line\n", encoding="utf-8"
    )
    (tmp_path / "notes.md").write_text(
        "calendar window here but not a results page\n", encoding="utf-8"
    )
    hits = av.tried_before("calendar window", tmp_path)
    assert [h["file"] for h in hits] == ["x-results.md"]
    assert av.tried_before("grid", tmp_path)[0]["file"] == "TRIAL_REGISTER.md"
    assert av.tried_before("", tmp_path) == []


def test_the_forward_view_lists_s3n_c1_and_registered_structures(tmp_path, monkeypatch):
    (tmp_path / "s3n.json").write_text(
        json.dumps({"ledgers": {"L1": {"completed": 2, "realistic_net": 300,
                                       "status": {"state": "running", "trades_to_go": 24}}}}), encoding="utf-8")  # fmt: skip
    (tmp_path / "c1.csv").write_text(
        "session,nav,buy_notional\n2026-11-02,100000,0\n2026-11-27,100090,18900\n", encoding="utf-8"
    )
    monkeypatch.setenv("ALGO_FORWARD_S3N_REPORT", str(tmp_path / "s3n.json"))
    monkeypatch.setenv("ALGO_FORWARD_C1_CSV", str(tmp_path / "c1.csv"))
    monkeypatch.setenv("ALGO_FORWARD_EOD_DIR", str(tmp_path / "none"))
    rows = av.forward_status()
    assert [r["name"][:6] for r in rows] == ["Weekly", "Month-"]
    assert (
        rows[0]["trades_to_go"] == 24
        and rows[1]["completed"] == 1
        and rows[1]["trades_to_go"] == 23
    )
    assert rows[1]["net"] == 90


@pytest.mark.parametrize(
    "name", ["forward_status", "register_status", "validate_draft", "tried_before"]
)
def test_every_public_view_exists(name):
    assert callable(getattr(av, name))
