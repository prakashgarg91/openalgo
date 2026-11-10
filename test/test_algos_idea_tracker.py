"""The Auto Builder idea tracker: read only, built from the register's own records."""

from datetime import datetime

import pytest

from services.algos import idea_tracker as tracker
from services.algos import registry as reg
from test.test_algos_registry_api import client, draft  # noqa: F401  (fixture reuse)


def test_the_hurdle_grows_with_the_number_of_ideas_tried():
    few = tracker.luck_hurdle(1, 0.025)
    many = tracker.luck_hurdle(325, 0.025)
    assert 1.9 < few < 2.0  # one idea: the usual one-sided 2.5 percent bar
    assert 3.7 < many < 3.9  # 325 ideas: the bar 0.025 / 325 is much stricter
    assert many > few


def test_the_hurdle_refuses_a_count_below_one():
    with pytest.raises(ValueError):
        tracker.luck_hurdle(0, 0.025)


def record(name, status, failed=(), forward=None, post_mortem=False):
    forward = dict(forward) if forward else None
    if forward is not None and post_mortem:
        forward["post_mortem"] = {"text": "x" * 70}
    return {
        "id": name.lower().replace(" ", "-"),
        "created_at": "2027-01-04T10:00:00",
        "slot": "2027-01",
        "trial_numbers": [321, 321],
        "status": status,
        "run": {"failed": list(failed)} if status != "registered" else None,
        "forward": forward,
        "content": {"name": name, "why_it_might_work": "w", "how_it_fails": "f"},
    }


def test_lessons_count_the_gates_ideas_missed_most_often():
    rows = [
        record("A", "rejected", ["beats the hold", "positive at doubled costs"]),
        record("B", "rejected", ["beats the hold"]),
        record("C", "eligible for a forward test"),
    ]
    assert tracker.lessons(rows)[0] == {"gate": "beats the hold", "ideas_missed": 2}
    assert len(tracker.lessons(rows)) == 2


def test_the_view_marks_a_changed_record_as_not_trusted_and_lists_stages():
    rows = [record("Good", "registered"), record("Edited", "rejected", ["g"])]
    view = tracker.build(rows, {"good"}, 322, 0.025, "2027-02", [])
    stages = {i["name"]: i["stage"] for i in view["ideas"]}
    assert stages["Good"] == "Written down, not yet tested"
    assert "not trusted" in stages["Edited"]
    assert view["live_gate"] == "locked"
    assert view["pass_bar"] == pytest.approx(0.025 / 322)


def test_a_forward_result_without_a_post_mortem_says_it_is_owed():
    owed = record("P", "forward pass", forward={"verdict": "pass"})
    done = record("Q", "forward pass", forward={"verdict": "pass"}, post_mortem=True)
    view = tracker.build([owed, done], {"p", "q"}, 322, 0.025, "2027-02", [])
    stages = {i["name"]: i["stage"] for i in view["ideas"]}
    assert "post-mortem is still owed" in stages["P"]
    assert "owed" not in stages["Q"]


def test_the_endpoint_is_read_only_and_reports_the_seeded_count(client, monkeypatch):  # noqa: F811
    from services.algos import agent_view

    monkeypatch.setattr(agent_view, "forward_status", lambda: [])
    body = client.get("/algos/api/idea-tracker").get_json()["data"]
    assert body["trial_count"] == reg.SEED_TRIALS and body["ideas"] == []
    assert body["live_gate"] == "locked" and body["next_free_month"] == "2027-01"
    client.post("/algos/api/registry", json=draft())
    body = client.get("/algos/api/idea-tracker").get_json()["data"]
    assert body["trial_count"] == reg.SEED_TRIALS + 1
    assert body["ideas"][0]["intact"] is True
    assert client.post("/algos/api/idea-tracker").status_code == 405
    assert datetime  # imported for clarity of the fixture's fixed clock
