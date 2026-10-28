"""The weekly pass: when it runs, what it asks for, and that it only ever proposes."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from test_algos_lab import history  # noqa: F401  (fixture)

from services.algos import (
    builder,
    builder_jobs,
    builder_run,
    chooser_store,
    custom,
    lab,
    maintenance,
)

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def _built(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M UTC")


def test_a_missing_or_old_table_is_stale_a_fresh_one_is_not():
    assert maintenance.table_is_stale(None, NOW)
    assert maintenance.table_is_stale({"algos": {}}, NOW)
    assert maintenance.table_is_stale({"built_at": "garbage"}, NOW)
    assert maintenance.table_is_stale({"built_at": _built(8)}, NOW)
    assert not maintenance.table_is_stale({"built_at": _built(2)}, NOW)


def test_request_asks_for_a_rebuild_only_when_stale_and_lists_built_algos(monkeypatch):
    spec = builder.Spec("condor", 2, 5, ("calm",), "skip")
    monkeypatch.setitem(custom.CUSTOM_SPECS, "custom_9", spec)
    monkeypatch.setitem(custom.ALGOS, "custom_9", custom.ALGOS["calm_condor"])
    fresh = maintenance.build_request(date(2026, 10, 28), {"built_at": _built(1)}, NOW)
    stale = maintenance.build_request(date(2026, 10, 28), {"built_at": _built(30)}, NOW)
    assert not fresh["rebuild_chooser"] and stale["rebuild_chooser"]
    assert fresh["customs"] == {"custom_9": spec.to_dict()}
    assert (
        "custom_9" in stale["chooser"]["customs"] and "smart_pick" not in stale["chooser"]["algos"]
    )


def test_nothing_to_do_starts_no_process(monkeypatch):
    started = []
    monkeypatch.setattr(builder_jobs, "start", lambda user, req: started.append(req))
    monkeypatch.setattr(
        chooser_store,
        "load_table",
        lambda path=None: {"built_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")},
    )
    monkeypatch.setattr(maintenance.custom, "CUSTOM_SPECS", {})
    assert maintenance.run_weekly() is None and not started


def test_stale_table_starts_one_system_job(monkeypatch):
    started = []
    monkeypatch.setattr(
        builder_jobs, "start", lambda user, req: started.append((user, req)) or "0123456789abcdef"
    )
    monkeypatch.setattr(chooser_store, "load_table", lambda path=None: None)
    assert maintenance.run_weekly() == "0123456789abcdef"
    assert started[0][0] == "system" and started[0][1]["kind"] == "maintenance"


def test_a_busy_engine_skips_the_week_quietly(monkeypatch):
    def busy(user, req):
        raise builder_jobs.Busy("running")

    monkeypatch.setattr(builder_jobs, "start", busy)
    monkeypatch.setattr(chooser_store, "load_table", lambda path=None: None)
    assert maintenance.run_weekly() is None


def test_the_job_is_scheduled_for_sunday_morning(monkeypatch):
    added = {}

    class Sched:
        def add_job(self, **kw):
            added.update(kw)

    from services.strategy_module import scheduler

    monkeypatch.setattr(scheduler, "get_scheduler", lambda: Sched())
    assert maintenance.install_job()
    assert added["id"] == maintenance.JOB_ID and added["max_instances"] == 1
    assert str(added["trigger"]).startswith("cron[") and "day_of_week='sun'" in str(
        added["trigger"]
    )


def test_maintenance_writes_proposals_and_changes_nothing_else(tmp_path, monkeypatch, history):  # noqa: F811
    monkeypatch.setattr(lab, "load_history", lambda *a, **k: history)
    job = tmp_path / "abcdef0123456789"
    job.mkdir()
    spec = builder.Spec("condor", 2, 5, ("calm",), "skip").to_dict()
    request = {
        "kind": "maintenance",
        "today": "2026-10-28",
        "customs": {"custom_9": spec},
        "model": "conservative",
    }
    (job / "request.json").write_text(json.dumps(request))
    builder_run.run(job)
    saved = json.loads((tmp_path / "proposals.json").read_text())
    assert set(saved["custom_9"]) == {"checked_on", "proposal", "verdict", "trials"}
    assert saved["custom_9"]["checked_on"] == "2026-10-28" and saved["custom_9"]["trials"] == 60
    assert json.loads((job / "result.json").read_text())["kind"] == "maintenance"
