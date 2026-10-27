"""The /algos API: refusals, ownership, and the Live confirmation."""

from datetime import datetime

import pytest
import pytz
from flask import Blueprint, Flask

from blueprints import algos
from database import algo_db
from database import strategy_module_db as sm_store
from limiter import limiter
from services.algos import runner
from services.algos.context import RegimeResult

USER = "algo_api_user"
OTHER = "algo_api_other"
# 500000 capital, 75 lot, 150 point width, 10 percent cap -> 4 lots * 11250
CEILING = 45000.0


def _regime():
    return RegimeResult(
        label="calm", bias="neutral", score=0.0, confidence=1.0, reasons=("ok",), missing=()
    )


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    algo_db.init_db()
    sm_store.init_db()
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(runner, "nifty_lot_size", lambda: 75)
    monkeypatch.setattr(runner, "days_to_expiry", lambda api_key, today=None: 4)
    monkeypatch.setattr(runner, "_api_key", lambda user: "key")
    monkeypatch.setattr(runner, "current_regime", lambda key: (_regime(), None))
    monkeypatch.setattr(runner, "_sync_strategy_jobs", lambda *a, **k: None)
    monkeypatch.setattr(runner, "sync_job", lambda *a, **k: True)
    monkeypatch.setattr(runner, "remove_job", lambda *a, **k: None)
    monkeypatch.setenv("ALGO_LIVE_MIN_SANDBOX_RUNS", "0")
    algos._regime_cache.clear()
    _wipe()
    yield
    _wipe()


def _wipe():
    for user in (USER, OTHER):
        for dep in algo_db.list_deployments(user):
            algo_db.delete_deployment(dep["id"], user)
        for row in sm_store.db_session.query(sm_store.SmStrategy).filter_by(user_id=user).all():
            row.status = "stopped"
        sm_store.db_session.commit()
        for row in sm_store.db_session.query(sm_store.SmStrategy).filter_by(user_id=user).all():
            sm_store.delete_strategy(row.id, user)
    algo_db.db_session.remove()
    sm_store.db_session.remove()


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config.update(TESTING=True, SECRET_KEY="algos-tests", PROPAGATE_EXCEPTIONS=True)
    application.register_blueprint(algos.algos_bp)
    # The session check redirects a logged-out caller to the login page.
    auth = Blueprint("auth", __name__)
    auth.add_url_rule("/auth/login", "login", lambda: ("login", 200))
    application.register_blueprint(auth)
    return application


def _login(client, user):
    with client.session_transaction() as s:
        s["logged_in"] = True
        s["user"] = user
        s["login_time"] = datetime.now(pytz.timezone("Asia/Kolkata")).isoformat()


@pytest.fixture
def client(app):
    c = app.test_client()
    _login(c, USER)
    return c


def _deploy(client, algo="zen", capital=500000):
    return client.post("/algos/api/deployments", json={"algo_id": algo, "capital": capital})


def test_logged_out_is_refused(app):
    assert app.test_client().get("/algos/api/catalogue").status_code in (401, 302)


def test_catalogue_lists_every_algo_undeployed(client):
    body = client.get("/algos/api/catalogue").get_json()
    assert [a["id"] for a in body["data"]] == ["zen", "mirror_zen", "morning_gap", "calm_condor"]
    assert all(a["deployment"] is None for a in body["data"])


def test_regime_endpoint_returns_the_snapshot(client):
    body = client.get("/algos/api/regime").get_json()
    assert body["data"]["label"] == "calm" and body["data"]["confidence"] == 1.0


@pytest.mark.parametrize(
    "payload",
    [
        {"algo_id": "nope", "capital": 500000},
        {"algo_id": "zen", "capital": "lots"},
        {"algo_id": "zen", "capital": True},
        {"algo_id": "zen", "capital": 5},
        {"algo_id": "zen", "capital": 10**12},
        {"algo_id": "zen"},
    ],
)
def test_deploy_rejects_bad_payloads(client, payload):
    assert client.post("/algos/api/deployments", json=payload).status_code == 400


def test_deploy_is_stopped_sandbox_and_shows_the_ceiling(client):
    r = _deploy(client)
    assert r.status_code == 201
    d = r.get_json()["data"]
    assert d["active"] is False and d["mode"] == "sandbox" and d["live_enabled"] is False
    assert d["max_loss_ceiling_inr"] == CEILING
    assert _deploy(client).status_code == 409


def test_deploy_too_small_returns_the_reason(client):
    r = _deploy(client, capital=20000)
    assert r.status_code == 400 and "capital" in r.get_json()["message"].lower()


def test_somebody_elses_algo_is_404_not_403(app, client):
    dep_id = _deploy(client).get_json()["data"]["id"]
    other = app.test_client()
    _login(other, OTHER)
    for method, path in (
        ("get", f"/algos/api/deployments/{dep_id}"),
        ("post", f"/algos/api/deployments/{dep_id}/active"),
        ("post", f"/algos/api/deployments/{dep_id}/live"),
        ("post", f"/algos/api/deployments/{dep_id}/run-now"),
        ("delete", f"/algos/api/deployments/{dep_id}"),
    ):
        r = getattr(other, method)(path, json={"active": True, "enabled": True})
        assert r.status_code == 404, path


def test_turning_on_validates_the_flag(client):
    dep_id = _deploy(client).get_json()["data"]["id"]
    assert (
        client.post(f"/algos/api/deployments/{dep_id}/active", json={"active": "yes"}).status_code
        == 400
    )
    r = client.post(f"/algos/api/deployments/{dep_id}/active", json={"active": True})
    assert r.status_code == 200 and r.get_json()["data"]["active"] is True


@pytest.mark.parametrize("confirm", [None, "45000", 1000, True])
def test_going_live_needs_the_exact_worst_case_loss(client, confirm):
    dep_id = _deploy(client).get_json()["data"]["id"]
    body = {"enabled": True}
    if confirm is not None:
        body["confirm_max_loss"] = confirm
    r = client.post(f"/algos/api/deployments/{dep_id}/live", json=body)
    assert r.status_code == 400
    assert r.get_json()["max_loss_ceiling_inr"] == CEILING
    got = algo_db.get_deployment(dep_id)
    assert got["mode"] == "sandbox"


def test_going_live_with_the_right_number_then_back_to_sandbox(client):
    dep_id = _deploy(client).get_json()["data"]["id"]
    r = client.post(
        f"/algos/api/deployments/{dep_id}/live", json={"enabled": True, "confirm_max_loss": CEILING}
    )
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["mode"] == "live" and d["live_enabled"] is True
    r = client.post(f"/algos/api/deployments/{dep_id}/live", json={"enabled": False})
    d = r.get_json()["data"]
    assert d["mode"] == "sandbox" and d["live_enabled"] is False


def test_mode_cannot_change_while_a_position_is_open(client):
    dep = _deploy(client).get_json()["data"]
    sm_store.claim_strategy_for_run(dep["strategy_id"])
    r = client.post(
        f"/algos/api/deployments/{dep['id']}/live",
        json={"enabled": True, "confirm_max_loss": CEILING},
    )
    assert r.status_code == 409


def test_run_now_needs_the_algo_on_and_records_a_decision(client, monkeypatch):
    dep_id = _deploy(client).get_json()["data"]["id"]
    assert client.post(f"/algos/api/deployments/{dep_id}/run-now").status_code == 409
    client.post(f"/algos/api/deployments/{dep_id}/active", json={"active": True})
    monkeypatch.setattr(runner, "run_entry", lambda i: {"action": "skip", "reason": "test"})
    r = client.post(f"/algos/api/deployments/{dep_id}/run-now")
    assert r.status_code == 200 and r.get_json()["data"]["reason"] == "test"


def test_remove_deletes_the_algo(client):
    dep_id = _deploy(client).get_json()["data"]["id"]
    assert client.delete(f"/algos/api/deployments/{dep_id}").status_code == 200
    assert client.get(f"/algos/api/deployments/{dep_id}").status_code == 404


def _closed_run(strategy_id, pnl):
    from datetime import UTC
    from datetime import datetime as dt

    now = dt.now(UTC).replace(tzinfo=None)
    run = sm_store.SmStrategyRun(
        strategy_id=strategy_id, mode="sandbox", started_at=now, stopped_at=now, pnl_realized=pnl
    )
    sm_store.db_session.add(run)
    sm_store.db_session.commit()


def _go_live(client, dep_id):
    return client.post(
        f"/algos/api/deployments/{dep_id}/live", json={"enabled": True, "confirm_max_loss": CEILING}
    )


def test_live_is_refused_without_a_sandbox_record(client, monkeypatch):
    monkeypatch.setenv("ALGO_LIVE_MIN_SANDBOX_RUNS", "3")
    dep = _deploy(client).get_json()["data"]
    assert dep["live_gate"]["allowed"] is False
    r = _go_live(client, dep["id"])
    assert r.status_code == 403 and "Sandbox" in r.get_json()["message"]
    assert algo_db.get_deployment(dep["id"])["mode"] == "sandbox"


def test_live_is_refused_when_the_sandbox_record_loses_money(client, monkeypatch):
    monkeypatch.setenv("ALGO_LIVE_MIN_SANDBOX_RUNS", "3")
    dep = _deploy(client).get_json()["data"]
    for pnl in (500, -900, 100):
        _closed_run(dep["strategy_id"], pnl)
    r = _go_live(client, dep["id"])
    assert r.status_code == 403 and "not profitable" in r.get_json()["message"]


def test_live_is_allowed_after_a_profitable_sandbox_record(client, monkeypatch):
    monkeypatch.setenv("ALGO_LIVE_MIN_SANDBOX_RUNS", "3")
    dep = _deploy(client).get_json()["data"]
    for pnl in (500, -200, 900):
        _closed_run(dep["strategy_id"], pnl)
    r = _go_live(client, dep["id"])
    assert r.status_code == 200 and r.get_json()["data"]["mode"] == "live"
    assert r.get_json()["data"]["live_gate"]["record"]["runs"] == 3


def test_coverage_endpoint(client):
    body = client.get("/algos/api/coverage").get_json()["data"]
    assert body["stands_aside_on"] == ["volatile", "event"]


def test_catalogue_exposes_evidence_and_status(client):
    items = {a["id"]: a for a in client.get("/algos/api/catalogue").get_json()["data"]}
    assert items["mirror_zen"]["status"] == "experimental"
    assert "real NSE option prices" in items["zen"]["evidence"]


def test_catalogue_tells_the_page_when_each_algo_checks(client):
    items = {a["id"]: a for a in client.get("/algos/api/catalogue").get_json()["data"]}
    assert items["zen"]["entry_time"] == "15:05"
    assert items["morning_gap"]["entry_time"] == "09:25"
    assert items["morning_gap"]["overnight"] is False
