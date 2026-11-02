"""The registration-first record: frozen, counted, one slot a month, one run, no promotion."""

from datetime import datetime

import pytest

from services.algos import registry as reg

NOV = datetime(2026, 11, 2, 10, 0)
JAN = datetime(2027, 1, 4, 10, 0)
FEB = datetime(2027, 2, 1, 10, 0)


def draft(**over):
    base = {
        "name": "Vol scaled equity gold",
        "idea": "Hold less equity when forecast volatility is high, more when it is low.",
        "instrument": "NIFTYBEES and GOLDBEES",
        "entry": "At each month-end close set the weights from the volatility forecast.",
        "exit": "Rebalance at the next month-end close.",
        "size": "Rs 1,00,000 account, whole shares",
        "costs": "universe.py itemised schedule and its doubled variant",
        "benchmark": "A hold of the same average exposure",
        "why_it_might_work": "Volatility is the one thing found to be predictable.",
        "how_it_fails": "Published work says it rarely beats a same-exposure hold after costs.",
        "data_seen": "All ETF history to 6 November 2026",
        "data_unseen": "Forward sessions only, assessed once",
        "end_rule": "24 monthly decisions or 31 May 2029",
        "kill_rule": "Cumulative net at or below minus Rs 5,000",
        "gates": ["positive net at both cost levels", "beats the same-exposure hold"],
        "params": {"target_vol": 0.10, "cap": 1.0},
    }
    return {**base, **over}


def test_a_complete_draft_is_frozen_with_a_fingerprint_and_the_next_trial_number(tmp_path):
    record = reg.register(draft(), tmp_path, JAN)
    assert record["trial_numbers"] == [320, 320]
    assert record["pass_bar"] == pytest.approx(0.025 / 320)
    assert record["status"] == "registered" and record["run"] is None
    assert reg.intact(record)
    assert (tmp_path / f"{record['id']}.md").read_text(encoding="utf-8").startswith("# Vol scaled")
    assert reg.running_count(tmp_path) == 320


def test_an_incomplete_draft_is_refused_in_plain_words(tmp_path):
    with pytest.raises(reg.Refused, match="how it fails"):
        reg.register(draft(how_it_fails=""), tmp_path, JAN)
    with pytest.raises(reg.Refused, match="gates"):
        reg.register(draft(gates=[]), tmp_path, JAN)
    assert not list(tmp_path.glob("*.json"))


def test_a_grid_is_not_a_registration_because_every_setting_is_one_value(tmp_path):
    with pytest.raises(reg.Refused, match="more than one value"):
        reg.register(draft(params={"target_vol": [0.08, 0.10, 0.12]}), tmp_path, JAN)


def test_the_months_already_used_are_refused_and_the_next_free_one_is_named(tmp_path):
    with pytest.raises(reg.Refused, match="C1 month-end ETF window.*2027-01"):
        reg.register(draft(), tmp_path, NOV)
    with pytest.raises(reg.Refused, match="eight-structure screen"):
        reg.register(draft(), tmp_path, datetime(2026, 12, 15))


def test_one_new_idea_a_month(tmp_path):
    reg.register(draft(), tmp_path, JAN)
    with pytest.raises(reg.Refused, match="already registered.*2027-02"):
        reg.register(draft(name="Another idea"), tmp_path, datetime(2027, 1, 20))
    second = reg.register(draft(name="Another idea"), tmp_path, FEB)
    assert second["trial_numbers"] == [321, 321]


def test_a_multi_trial_registration_counts_every_trial(tmp_path):
    record = reg.register(draft(trials=8), tmp_path, JAN)
    assert record["trial_numbers"] == [320, 327]
    assert reg.running_count(tmp_path) == 327


def test_the_same_registration_cannot_be_written_twice(tmp_path):
    reg.register(draft(), tmp_path, JAN)
    with pytest.raises(reg.Refused):
        reg.register(
            draft(), tmp_path, FEB
        )  # identical content: same file, and a slot is not a reason


def test_editing_a_frozen_file_is_detected_and_blocks_the_run(tmp_path):
    record = reg.register(draft(), tmp_path, JAN)
    path = tmp_path / f"{record['id']}.json"
    tampered = path.read_text(encoding="utf-8").replace('"target_vol": 0.1,', '"target_vol": 0.2,')
    assert tampered != path.read_text(encoding="utf-8")  # the edit really changed the file
    path.write_text(tampered, encoding="utf-8")
    assert not reg.intact(reg.get(tmp_path, record["id"]))
    with pytest.raises(reg.Refused, match="changed after it was frozen"):
        reg.record_run(tmp_path, record["id"], dict.fromkeys(record["content"]["gates"], True), JAN)


def test_one_run_only_and_the_verdict_is_reject_or_eligible_never_an_edge(tmp_path):
    record = reg.register(draft(), tmp_path, JAN)
    gates = record["content"]["gates"]
    with pytest.raises(reg.Refused, match="every registered gate"):
        reg.record_run(tmp_path, record["id"], {gates[0]: True}, FEB)
    done = reg.record_run(tmp_path, record["id"], dict.fromkeys(gates, True), FEB)
    assert done["run"]["verdict"] == "eligible for a forward test"
    assert "edge" not in done["status"]
    with pytest.raises(reg.Refused, match="already been run"):
        reg.record_run(tmp_path, record["id"], dict.fromkeys(gates, True), FEB)


def test_a_failed_gate_rejects(tmp_path):
    record = reg.register(draft(), tmp_path, JAN)
    gates = record["content"]["gates"]
    done = reg.record_run(tmp_path, record["id"], {gates[0]: True, gates[1]: False}, FEB)
    assert done["status"] == "rejected" and done["run"]["failed"] == [gates[1]]


def test_an_unsafe_id_is_not_looked_up(tmp_path):
    assert reg.get(tmp_path, "../../etc/passwd") is None


def test_builder_searches_add_every_configuration_to_the_trial_count(tmp_path):
    assert reg.running_count(tmp_path) == 319
    reg.add_builder_trials(tmp_path, 60, "build your own search", JAN)
    reg.add_builder_trials(tmp_path, 40, "weekly re-check", JAN)
    reg.add_builder_trials(tmp_path, 0, "nothing tried", JAN)
    assert reg.builder_trials(tmp_path) == 100 and reg.running_count(tmp_path) == 419
    record = reg.register(draft(), tmp_path, JAN)
    assert record["trial_numbers"] == [420, 420]
