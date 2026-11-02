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


def eligible_record(tmp_path, algo_id="custom_1"):
    record = reg.register(draft(params={"algo_id": algo_id, "width": 100}), tmp_path, JAN)
    return reg.record_run(
        tmp_path, record["id"], dict.fromkeys(record["content"]["gates"], True), FEB
    )


def test_a_forward_result_needs_an_eligible_registration_and_is_recorded_once(tmp_path):
    registered = reg.register(draft(), tmp_path, JAN)
    with pytest.raises(reg.Refused, match="eligible for a forward test"):
        reg.record_forward(tmp_path, registered["id"], "pass", {}, FEB)
    done = eligible_record(tmp_path / "two", "custom_2")
    with pytest.raises(reg.Refused, match="pass, fail or inconclusive"):
        reg.record_forward(tmp_path / "two", done["id"], "edge shown", {}, FEB)
    ended = reg.record_forward(tmp_path / "two", done["id"], "pass", {"trades": 26}, FEB)
    assert ended["status"] == "forward pass"
    with pytest.raises(reg.Refused, match="already recorded"):
        reg.record_forward(tmp_path / "two", done["id"], "pass", {}, FEB)


def test_only_a_recorded_forward_pass_for_that_algo_counts(tmp_path):
    done = eligible_record(tmp_path, "custom_7")
    assert reg.forward_passed(tmp_path, "custom_7") is False
    reg.record_forward(tmp_path, done["id"], "pass", {}, FEB)
    assert reg.forward_passed(tmp_path, "custom_7") is True
    assert reg.forward_passed(tmp_path, "custom_8") is False


def test_a_setting_that_hides_a_grid_in_text_is_refused(tmp_path):
    for hidden in ("100|150|200", "100, 150", "100 to 200", "50..100", "a;b"):
        with pytest.raises(reg.Refused, match="several values or a range"):
            reg.register(draft(params={"width": hidden}), tmp_path, JAN)
    assert reg.register(draft(params={"label": "calm days"}), tmp_path, JAN)["trial_numbers"] == [
        320,
        320,
    ]


def test_the_trial_count_of_one_registration_is_bounded_and_a_tampered_file_cannot_get_a_result(
    tmp_path,
):
    with pytest.raises(reg.Refused, match="from 1 to 100"):
        reg.register(draft(trials=10_000), tmp_path, JAN)
    done = eligible_record(tmp_path)
    path = tmp_path / f"{done['id']}.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"width": 100', '"width": 300'),
        encoding="utf-8",
    )
    with pytest.raises(reg.Refused, match="changed after it was frozen"):
        reg.record_forward(tmp_path, done["id"], "pass", {}, FEB)


def test_one_unreadable_file_in_the_folder_does_not_break_the_register(tmp_path):
    reg.register(draft(), tmp_path, JAN)
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert reg.running_count(tmp_path) == 320 and len(reg._store(tmp_path)) == 1


def test_an_algo_that_is_not_in_the_app_cannot_be_named(tmp_path):
    with pytest.raises(reg.Refused, match="not one of the algos"):
        reg.register(draft(params={"algo_id": "made_up"}), tmp_path, JAN, {"zen", "calm_condor"})
    assert (
        reg.register(draft(params={"algo_id": "zen"}), tmp_path, JAN, {"zen"})["status"]
        == "registered"
    )
