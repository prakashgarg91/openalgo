"""Builder over HTTP: what a search may ask, who can read it, and what saving does."""

from datetime import datetime

import pytest
import pytz
from flask import Blueprint, Flask

from blueprints import algos
from database import algo_db
from database import strategy_module_db as sm_store
from limiter import limiter
from services.algos import builder_jobs, custom, runner
from services.algos.context import RegimeResult
from services.algos.templates import ALGOS, CUSTOM_SPECS

USER = "builder_api_user"
OTHER = "builder_api_other"
SPEC = {"family": "bull_put", "short": 2, "long": 5, "labels": ["calm"], "expiry": "skip"}


def _result(winner=True, edge=True):
    stats = {
        "trades": 90,
        "total": 5000.0,
        "profit_factor": 1.5,
        "avg": 55.0,
        "max_drawdown": -900.0,
    }
    return {
        "trials": 60,
        "verdict": {
            "edge_shown": edge,
            "headline": "It held up on data it was not chosen on.",
            "reasons": [],
        },
        "winner": {"spec": SPEC, "name": "Bull put", "test": stats} if winner else None,
    }


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    algo_db.init_db()
    sm_store.init_db()
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(runner, "nifty_lot_size", lambda: 75)
    monkeypatch.setattr(runner, "days_to_expiry", lambda api_key, today=None: 4)
    monkeypatch.setattr(runner, "_api_key", lambda user: "key")
    monkeypatch.setattr(
        runner,
        "current_regime",
        lambda key: (RegimeResult("calm", "neutral", 0.0, 1.0, ("ok",), ()), None),
    )
    monkeypatch.setattr(runner, "_sync_strategy_jobs", lambda *a, **k: None)
    monkeypatch.setattr(runner, "sync_job", lambda *a, **k: True)
    monkeypatch.setattr(runner, "remove_job", lambda *a, **k: None)
    algos._custom_loaded = True
    _wipe()
    yield
    _wipe()


def _wipe():
    for user in (USER, OTHER):
        for dep in algo_db.list_deployments(user):
            algo_db.delete_deployment(dep["id"], user)
        for row in algo_db.list_custom(user):
            algo_db.delete_custom(row["id"], user)
            custom.unregister(row["id"])
        for row in sm_store.db_session.query(sm_store.SmStrategy).filter_by(user_id=user).all():
            row.status = "stopped"
        sm_store.db_session.commit()
        for row in sm_store.db_session.query(sm_store.SmStrategy).filter_by(user_id=user).all():
            sm_store.delete_strategy(row.id, user)
    algo_db.db_session.remove()
    sm_store.db_session.remove()
    for key in [k for k in ALGOS if k.startswith("custom_")]:
        ALGOS.pop(key, None)
        CUSTOM_SPECS.pop(key, None)


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config.update(TESTING=True, SECRET_KEY="builder-tests", PROPAGATE_EXCEPTIONS=True)
    application.register_blueprint(algos.algos_bp)
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


@pytest.fixture
def jobs(monkeypatch):
    state = {"started": [], "status": {}}

    def start(user, req):
        state["started"].append((user, req))
        return "0123456789abcdef"

    monkeypatch.setattr(builder_jobs, "start", start)
    monkeypatch.setattr(
        builder_jobs, "status", lambda job_id, user: state["status"].get((job_id, user))
    )
    return state


def test_search_starts_a_background_job(client, jobs):
    response = client.post(
        "/algos/api/builder/search", json={"families": ["condor"], "label_sets": [["calm"]]}
    )
    assert response.status_code == 202 and response.get_json()["job_id"] == "0123456789abcdef"
    assert jobs["started"][0][0] == USER and jobs["started"][0][1]["model"] == "conservative"


@pytest.mark.parametrize(
    "payload",
    [
        {"families": []},
        {"families": ["naked_put"]},
        {"families": ["condor"], "label_sets": []},
        {"families": ["condor"], "label_sets": [["moonless"]]},
        {"families": ["condor"], "label_sets": "calm"},
        {"families": ["condor"], "model": "magic"},
        {"label_sets": [["calm"], ["calm", "trending"], ["trending"], ["volatile"]]},
    ],
)
def test_search_refuses_bad_requests_in_plain_words(client, jobs, payload):
    response = client.post("/algos/api/builder/search", json=payload)
    assert response.status_code == 400 and response.get_json()["message"]
    assert not jobs["started"]


def test_a_second_search_while_one_runs_is_a_conflict(client, monkeypatch):
    def busy(user, req):
        raise builder_jobs.Busy("A search is already running. It takes about a minute.")

    monkeypatch.setattr(builder_jobs, "start", busy)
    assert client.post("/algos/api/builder/search", json={}).status_code == 409


def test_job_is_private_to_its_owner(app, client, jobs):
    jobs["status"][("0123456789abcdef", USER)] = {"state": "running", "progress": {"done": 3}}
    assert (
        client.get("/algos/api/builder/jobs/0123456789abcdef").get_json()["data"]["state"]
        == "running"
    )
    other = app.test_client()
    _login(other, OTHER)
    assert other.get("/algos/api/builder/jobs/0123456789abcdef").status_code == 404


def test_saving_adds_the_algo_to_the_catalogue_as_experimental(client, jobs):
    jobs["status"][("0123456789abcdef", USER)] = {"state": "done", "result": _result()}
    response = client.post(
        "/algos/api/builder/save", json={"job_id": "0123456789abcdef", "name": "My put"}
    )
    assert response.status_code == 201
    algo_id = response.get_json()["data"]["algo_id"]
    items = {a["id"]: a for a in client.get("/algos/api/catalogue").get_json()["data"]}
    mine = items[algo_id]
    assert mine["name"] == "My put" and mine["status"] == "experimental"
    assert "Built by you" in mine["evidence"] and "not proof" not in mine["evidence"]


def test_saving_needs_a_finished_search_with_a_winner_and_a_name(client, jobs):
    jobs["status"][("0123456789abcdef", USER)] = {"state": "running", "progress": {"done": 1}}
    assert (
        client.post(
            "/algos/api/builder/save", json={"job_id": "0123456789abcdef", "name": "x"}
        ).status_code
        == 400
    )
    jobs["status"][("0123456789abcdef", USER)] = {"state": "done", "result": _result(winner=False)}
    assert (
        client.post(
            "/algos/api/builder/save", json={"job_id": "0123456789abcdef", "name": "x"}
        ).status_code
        == 400
    )
    jobs["status"][("0123456789abcdef", USER)] = {"state": "done", "result": _result()}
    assert (
        client.post(
            "/algos/api/builder/save", json={"job_id": "0123456789abcdef", "name": ""}
        ).status_code
        == 400
    )
    assert (
        client.post("/algos/api/builder/save", json={"job_id": "nope", "name": "x"}).status_code
        == 400
    )


def test_a_built_algo_deploys_to_sandbox_through_the_same_path(client, jobs):
    jobs["status"][("0123456789abcdef", USER)] = {"state": "done", "result": _result(edge=False)}
    algo_id = client.post(
        "/algos/api/builder/save", json={"job_id": "0123456789abcdef", "name": "My put"}
    ).get_json()["data"]["algo_id"]
    deployed = client.post("/algos/api/deployments", json={"algo_id": algo_id, "capital": 500000})
    body = deployed.get_json()["data"]
    assert deployed.status_code == 201 and body["mode"] == "sandbox" and body["active"] is False
    # 150 points wide, 75 lot, 10 percent of 5 lakh -> 4 lots
    assert body["max_loss_ceiling_inr"] == 4 * 150 * 75


def test_delete_refuses_while_deployed_then_removes(client, jobs):
    jobs["status"][("0123456789abcdef", USER)] = {"state": "done", "result": _result()}
    algo_id = client.post(
        "/algos/api/builder/save", json={"job_id": "0123456789abcdef", "name": "My put"}
    ).get_json()["data"]["algo_id"]
    row_id = int(algo_id.split("_")[1])
    dep = client.post(
        "/algos/api/deployments", json={"algo_id": algo_id, "capital": 500000}
    ).get_json()["data"]
    assert client.delete(f"/algos/api/builder/custom/{row_id}").status_code == 409
    client.delete(f"/algos/api/deployments/{dep['id']}")
    assert client.delete(f"/algos/api/builder/custom/{row_id}").status_code == 200
    assert algo_id not in ALGOS


def test_someone_elses_built_algo_cannot_be_deleted(app, client, jobs):
    jobs["status"][("0123456789abcdef", USER)] = {"state": "done", "result": _result()}
    algo_id = client.post(
        "/algos/api/builder/save", json={"job_id": "0123456789abcdef", "name": "Mine"}
    ).get_json()["data"]["algo_id"]
    other = app.test_client()
    _login(other, OTHER)
    assert (
        other.delete(f"/algos/api/builder/custom/{int(algo_id.split('_')[1])}").status_code == 404
    )
    assert algo_id in ALGOS
