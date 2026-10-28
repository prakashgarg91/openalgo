import json

import pytest

from services.algos import builder_jobs as jobs


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    return tmp_path


def _job(root, name, user="me", **files):
    folder = root / name
    folder.mkdir()
    (folder / "request.json").write_text(json.dumps({"user": user}))
    for fname, payload in files.items():
        (folder / f"{fname}.json").write_text(json.dumps(payload))
    return name


@pytest.mark.parametrize(
    "bad", ["", "../etc", "0123456789abcde", "0123456789abcdeg", "0123456789ABCDEF", None]
)
def test_only_sixteen_hex_characters_name_a_job(bad):
    assert not jobs.valid_id(bad)


def test_status_is_private_and_reads_results(root):
    done = _job(root, "0123456789abcdef", result={"trials": 3})
    assert jobs.status(done, "me") == {"state": "done", "result": {"trials": 3}}
    assert jobs.status(done, "someone-else") is None
    assert jobs.status("../../x", "me") is None
    assert jobs.status("ffffffffffffffff", "me") is None


def test_error_and_interruption_are_explained(root):
    failed = _job(root, "aaaaaaaaaaaaaaaa", error={"message": "No history."})
    assert jobs.status(failed, "me") == {"state": "failed", "message": "No history."}
    orphan = _job(root, "bbbbbbbbbbbbbbbb")
    state = jobs.status(orphan, "me")
    assert state["state"] == "failed" and "interrupted" in state["message"]


def test_one_search_at_a_time(root, monkeypatch):
    monkeypatch.setitem(jobs._running, "x", object())
    with pytest.raises(jobs.Busy):
        jobs.start("me", {})
