"""Runner: deploy, the daily entry decision, and scheduling."""

from datetime import date

import pytest

from database import algo_db
from database import strategy_module_db as sm_store
from services.algos import runner
from services.algos.context import RegimeResult
from services.strategy_module import engine as sm_engine
from services.strategy_module import scheduler as sm_scheduler

USER = "algo_runner_user"
WEEKDAY = date(2026, 10, 28)


def _regime(label="calm", bias="neutral", confidence=1.0):
    return RegimeResult(
        label=label, bias=bias, score=0.0, confidence=confidence, reasons=("test",), missing=()
    )


@pytest.fixture(autouse=True)
def env(monkeypatch):
    algo_db.init_db()
    sm_store.init_db()
    monkeypatch.setattr(runner, "nifty_lot_size", lambda: 75)
    monkeypatch.setattr(runner, "days_to_expiry", lambda api_key, today=None: 4)
    monkeypatch.setattr(runner, "_api_key", lambda user: "key")
    monkeypatch.setattr(runner, "_is_holiday", lambda day: False)
    monkeypatch.setattr(runner, "current_regime", lambda key: (_regime(), None))
    started = []

    class Result:
        ok = True
        run_id = 11
        error = None

    def fake_start(strategy_id, user_id, mode, trigger_source="manual", **kw):
        started.append((strategy_id, mode, trigger_source))
        return Result()

    monkeypatch.setattr(sm_engine, "start_run", fake_start)
    monkeypatch.setattr(runner, "_sync_strategy_jobs", lambda *a, **k: None)
    _wipe()
    yield started
    _wipe()


def _wipe():
    """Remove this user's deployments and strategies, even a one left running."""
    for dep in algo_db.list_deployments(USER):
        algo_db.delete_deployment(dep["id"], USER)
    for row in sm_store.db_session.query(sm_store.SmStrategy).filter_by(user_id=USER).all():
        row.status = "stopped"
    sm_store.db_session.commit()
    for row in sm_store.db_session.query(sm_store.SmStrategy).filter_by(user_id=USER).all():
        sm_store.delete_strategy(row.id, USER)
    algo_db.db_session.remove()
    sm_store.db_session.remove()


def _deploy(algo="zen", capital=500_000, active=True, mode="sandbox"):
    dep, err = runner.deploy(USER, algo, capital)
    assert err is None, err
    algo_db.update_deployment(dep["id"], USER, active=active, mode=mode)
    return dep


def test_deploy_creates_a_stopped_sandbox_algo_with_a_valid_strategy():
    dep, err = runner.deploy(USER, "zen", 500_000)
    assert err is None
    assert dep["active"] is False and dep["mode"] == "sandbox"
    row = sm_store.get_strategy(dep["strategy_id"], USER)
    assert row.strategy_type == "positional" and row.live_enabled is False
    assert row.exit_time is not None and row.entry_time is None


def test_deploy_refuses_capital_too_small_with_the_reason():
    dep, err = runner.deploy(USER, "zen", 20_000)
    assert dep is None and "capital" in err.lower()


def test_deploy_refuses_unknown_algo_and_duplicate():
    assert runner.deploy(USER, "nope", 500_000)[0] is None
    assert runner.deploy(USER, "zen", 500_000)[1] is None
    dep, err = runner.deploy(USER, "zen", 500_000)
    assert dep is None and "already" in err


def test_calm_day_starts_a_sandbox_run_and_logs_the_trade(env):
    dep = _deploy()
    out = runner.run_entry(dep["id"], today=WEEKDAY)
    assert out["action"] == "trade" and out["run_id"] == 11
    assert env == [(dep["strategy_id"], "sandbox", "scheduler")]
    log = algo_db.list_decisions(dep["id"])
    assert log[0]["action"] == "trade" and log[0]["lots"] == 4 and log[0]["side"] == "bull_put"
    row = sm_store.get_strategy(dep["strategy_id"], USER)
    assert {leg["option_type"] for leg in row.legs} == {"PE"}


def test_bearish_day_rewrites_the_legs_to_a_bear_call(monkeypatch, env):
    dep = _deploy()
    monkeypatch.setattr(runner, "current_regime", lambda k: (_regime("trending", "bearish"), None))
    runner.run_entry(dep["id"], today=WEEKDAY)
    row = sm_store.get_strategy(dep["strategy_id"], USER)
    assert {leg["option_type"] for leg in row.legs} == {"CE"}


def test_event_day_stands_aside_with_a_reason(monkeypatch, env):
    dep = _deploy()
    monkeypatch.setattr(runner, "current_regime", lambda k: (_regime("event"), None))
    out = runner.run_entry(dep["id"], today=WEEKDAY)
    assert out["action"] == "skip" and "event" in out["reason"].lower()
    assert env == []
    assert algo_db.list_decisions(dep["id"])[0]["regime_label"] == "event"


def test_stopped_deployment_does_nothing(env):
    dep = _deploy(active=False)
    assert runner.run_entry(dep["id"], today=WEEKDAY)["action"] == "skip"
    assert env == [] and algo_db.list_decisions(dep["id"]) == []


def test_holiday_skips(monkeypatch, env):
    dep = _deploy()
    monkeypatch.setattr(runner, "_is_holiday", lambda day: True)
    out = runner.run_entry(dep["id"], today=WEEKDAY)
    assert out["action"] == "skip" and "closed" in out["reason"].lower() and env == []


def test_open_position_blocks_a_second_entry(env):
    dep = _deploy()
    sm_store.claim_strategy_for_run(dep["strategy_id"])
    out = runner.run_entry(dep["id"], today=WEEKDAY)
    assert out["action"] == "skip" and "still open" in out["reason"] and env == []


def test_live_mode_without_strategy_opt_in_is_refused_not_started(monkeypatch):
    dep = _deploy(mode="live")

    class Refusal:
        ok = False
        run_id = None
        error = "This strategy is not enabled for live trading. Enable it first."

    monkeypatch.setattr(sm_engine, "start_run", lambda *a, **k: Refusal())
    out = runner.run_entry(dep["id"], today=WEEKDAY)
    assert out["action"] == "error" and "live" in out["reason"].lower()


def test_missing_api_key_is_a_plain_error(monkeypatch):
    dep = _deploy()
    monkeypatch.setattr(runner, "_api_key", lambda user: None)
    out = runner.run_entry(dep["id"], today=WEEKDAY)
    assert out["action"] == "error" and "api key" in out["reason"].lower()


def test_a_crash_is_recorded_not_raised(monkeypatch):
    dep = _deploy()

    def boom(key):
        raise RuntimeError("feed down")

    monkeypatch.setattr(runner, "current_regime", boom)
    out = runner.run_entry(dep["id"], today=WEEKDAY)
    assert out["action"] == "error"
    assert "RuntimeError" not in out["reason"] and "feed down" not in out["reason"]


def test_remove_refuses_while_a_position_is_open_then_cleans_up():
    dep = _deploy()
    sm_store.claim_strategy_for_run(dep["strategy_id"])
    ok, msg = runner.remove(dep["id"], USER)
    assert ok is False and "position" in msg.lower()
    sm_store.db_session.query(sm_store.SmStrategy).filter_by(id=dep["strategy_id"]).update(
        {"status": "stopped"}
    )
    sm_store.db_session.commit()
    ok, msg = runner.remove(dep["id"], USER)
    assert ok is True
    assert algo_db.get_deployment(dep["id"]) is None


def test_entry_job_is_installed_for_active_and_removed_for_stopped():
    sm_scheduler.start(paused=True)
    try:
        dep = _deploy(active=True)
        assert runner.sync_job(dep["id"]) is True
        assert sm_scheduler.get_scheduler().get_job(runner.job_id(dep["id"])) is not None
        algo_db.update_deployment(dep["id"], USER, active=False)
        runner.sync_job(dep["id"])
        assert sm_scheduler.get_scheduler().get_job(runner.job_id(dep["id"])) is None
    finally:
        sm_scheduler.shutdown()


def test_boot_time_sync_releases_its_database_session():
    """sync_all_jobs runs on the boot thread, where no request teardown fires."""
    algo_db.db_session.remove()
    runner.sync_all_jobs()
    assert algo_db.db_session.registry.has() is False
