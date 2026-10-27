"""Algo deployment store: ownership, uniqueness, and a bounded decision log."""

import pytest

from database import algo_db as store

USER = "algo_db_user"
OTHER = "algo_db_other"


@pytest.fixture(autouse=True)
def _clean():
    store.init_db()

    def wipe():
        for row in store.db_session.query(store.AlgoDeployment).filter(
            store.AlgoDeployment.user_id.in_([USER, OTHER])
        ):
            store.db_session.query(store.AlgoDecision).filter_by(deployment_id=row.id).delete()
            store.db_session.delete(row)
        store.db_session.commit()

    wipe()
    yield
    wipe()
    store.db_session.remove()


def test_deployment_is_born_stopped_and_in_sandbox():
    dep, err = store.create_deployment(USER, "zen", 7, 500000)
    assert err is None
    assert dep["active"] is False and dep["mode"] == "sandbox"
    assert dep["capital"] == 500000.0


def test_one_deployment_per_algo_per_user():
    assert store.create_deployment(USER, "zen", 1, 100000)[1] is None
    dep, err = store.create_deployment(USER, "zen", 2, 100000)
    assert dep is None and "already deployed" in err
    assert store.create_deployment(OTHER, "zen", 3, 100000)[1] is None


def test_other_users_cannot_read_or_change_a_deployment():
    dep, _ = store.create_deployment(USER, "zen", 1, 100000)
    assert store.get_deployment(dep["id"], OTHER) is None
    assert store.update_deployment(dep["id"], OTHER, active=True) is None
    assert store.delete_deployment(dep["id"], OTHER) is False
    assert store.get_deployment(dep["id"], USER)["active"] is False


def test_update_changes_only_allowed_fields():
    dep, _ = store.create_deployment(USER, "zen", 1, 100000)
    out = store.update_deployment(dep["id"], USER, active=True, strategy_id=99)
    assert out["active"] is True and out["strategy_id"] == 1


def test_active_only_filter():
    a, _ = store.create_deployment(USER, "zen", 1, 100000)
    store.create_deployment(USER, "mirror_zen", 2, 100000)
    store.update_deployment(a["id"], USER, active=True)
    assert [d["algo_id"] for d in store.list_deployments(USER, active_only=True)] == ["zen"]


def test_decisions_newest_first_and_validated():
    dep, _ = store.create_deployment(USER, "zen", 1, 100000)
    store.record_decision(dep["id"], "skip", "event day", regime_label="event")
    store.record_decision(dep["id"], "trade", "calm", lots=3, max_loss_inr=33750)
    got = store.list_decisions(dep["id"])
    assert [d["action"] for d in got] == ["trade", "skip"]
    assert got[0]["lots"] == 3 and got[0]["max_loss_inr"] == 33750.0
    with pytest.raises(ValueError):
        store.record_decision(dep["id"], "bogus", "x")


def test_decision_log_is_capped(monkeypatch):
    monkeypatch.setattr(store, "MAX_DECISIONS_PER_DEPLOYMENT", 5)
    dep, _ = store.create_deployment(USER, "zen", 1, 100000)
    for i in range(9):
        store.record_decision(dep["id"], "skip", f"day {i}")
    got = store.list_decisions(dep["id"])
    assert len(got) == 5 and got[0]["reason"] == "day 8"


def test_delete_removes_the_log_too():
    dep, _ = store.create_deployment(USER, "zen", 1, 100000)
    store.record_decision(dep["id"], "skip", "x")
    assert store.delete_deployment(dep["id"], USER) is True
    assert store.list_decisions(dep["id"]) == []
