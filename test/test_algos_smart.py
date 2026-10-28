"""Smart Pick, the chooser endpoints and the debugger endpoints, end to end over HTTP."""

from datetime import datetime

import pytest
import pytz
from flask import Blueprint, Flask
from test_algos_lab import history  # noqa: F401  (fixture)

from blueprints import algos
from database import algo_db
from database import strategy_module_db as sm_store
from limiter import limiter
from services.algos import builder_jobs, chooser, chooser_store, lab, runner
from services.algos.context import RegimeResult
from services.algos.templates import build

USER = "smart_user"
OTHER = "smart_other"


def _regime(label="calm", confidence=1.0):
    return RegimeResult(label, "bullish", 0.2, confidence, ("ok",), ())


def _good_table():
    """Zen earned calm days: strong in older years and still positive in newer ones."""
    good = [
        {
            "date": f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}",
            "regime": "calm",
            "pnl": 300.0 if i % 3 else -200.0,
        }
        for i in range(120)
    ]
    return chooser.build_table({"zen": good})


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
    monkeypatch.setattr(chooser_store, "load_table", lambda path=None: None)
    algos._custom_loaded = True
    algos._regime_cache.clear()
    algos._history_cache.clear()
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
    application.config.update(TESTING=True, SECRET_KEY="smart-tests", PROPAGATE_EXCEPTIONS=True)
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


def _plan(label="calm", **kw):
    return build("smart_pick", _regime(label), capital=500_000, lot_size=75, days_to_expiry=4, **kw)


# -- Smart Pick as a plan ---------------------------------------------------------


def test_smart_pick_runs_the_algo_the_chooser_picks(monkeypatch):
    monkeypatch.setattr(chooser_store, "load_table", lambda path=None: _good_table())
    plan = _plan()
    zen = build("zen", _regime(), capital=500_000, lot_size=75, days_to_expiry=4)
    assert plan.action == "trade" and plan.algo_id == "smart_pick"
    assert plan.reason.startswith("Picked Zen")
    assert plan.config["legs"] == zen.config["legs"] and plan.lots == zen.lots


def test_smart_pick_stands_aside_without_evidence_and_says_why():
    plan = _plan()
    assert plan.action == "skip" and "evidence table has not been built" in plan.reason


def test_smart_pick_stands_aside_on_a_day_nobody_earned(monkeypatch):
    monkeypatch.setattr(chooser_store, "load_table", lambda path=None: _good_table())
    plan = _plan("volatile")
    assert plan.action == "skip" and "no algo has earned a place on a volatile day" in plan.reason


def test_smart_pick_is_only_a_chooser_not_a_trade_of_its_own(monkeypatch):
    assert "smart_pick" not in chooser_store.candidate_ids()
    assert "morning_gap" not in chooser_store.candidate_ids()  # intraday, a different entry time


# -- Deploying and the Live ceiling ------------------------------------------------


def test_smart_pick_deploys_to_sandbox_with_a_ten_percent_ceiling(client):
    r = client.post("/algos/api/deployments", json={"algo_id": "smart_pick", "capital": 500000})
    body = r.get_json()["data"]
    assert r.status_code == 201 and body["mode"] == "sandbox" and body["active"] is False
    assert body["max_loss_ceiling_inr"] == 50_000.0


def test_the_catalogue_lists_smart_pick_as_experimental(client):
    items = {a["id"]: a for a in client.get("/algos/api/catalogue").get_json()["data"]}
    assert items["smart_pick"]["status"] == "experimental"


def test_lab_refuses_smart_pick_because_its_history_would_look_ahead(client):
    r = client.post("/algos/api/lab/run", json={"algo_id": "smart_pick"})
    assert r.status_code == 400 and "no history of its own" in r.get_json()["message"]


# -- Chooser endpoints -------------------------------------------------------------


def test_today_stands_aside_with_reasons_when_nobody_has_earned_the_day(client, monkeypatch):
    monkeypatch.setattr(chooser_store, "load_table", lambda path=None: _good_table())
    monkeypatch.setattr(runner, "current_regime", lambda key: (_regime("volatile"), None))
    body = client.get("/algos/api/chooser/today").get_json()["data"]
    assert body["decision"]["pick"] is None and body["regime"]["label"] == "volatile"
    assert body["table"]["rows"] and body["table"]["split"]


def test_today_picks_when_one_has_earned_it(client, monkeypatch):
    monkeypatch.setattr(chooser_store, "load_table", lambda path=None: _good_table())
    assert client.get("/algos/api/chooser/today").get_json()["data"]["decision"]["pick"] == "zen"


def test_rebuild_starts_a_background_job_over_the_overnight_algos(client, monkeypatch):
    started = []
    monkeypatch.setattr(
        builder_jobs, "start", lambda user, req: started.append(req) or "0123456789abcdef"
    )
    r = client.post("/algos/api/chooser/rebuild")
    assert r.status_code == 202
    assert started[0]["kind"] == "chooser"
    assert set(started[0]["algos"]) == {"zen", "mirror_zen", "calm_condor"}


def test_rebuild_while_busy_is_a_conflict(client, monkeypatch):
    def busy(user, req):
        raise builder_jobs.Busy("A search is already running. It takes about a minute.")

    monkeypatch.setattr(builder_jobs, "start", busy)
    assert client.post("/algos/api/chooser/rebuild").status_code == 409


# -- Debugger endpoints ------------------------------------------------------------


def test_debug_explains_a_day_in_steps(client, monkeypatch, history):  # noqa: F811
    monkeypatch.setattr(lab, "load_history", lambda *a, **k: history)
    traded = lab.run_lab(history, "zen").trades[0]["date"]
    body = client.post("/algos/api/debug", json={"algo_id": "zen", "date": traded}).get_json()[
        "data"
    ]
    assert body["date"] == traded and body["steps"] and "traded" in body["verdict"]


@pytest.mark.parametrize(
    "payload",
    [
        {"algo_id": "nope", "date": "2024-03-14"},
        {"algo_id": "smart_pick", "date": "2024-03-14"},
        {"algo_id": "zen"},
        {"algo_id": "zen", "date": "yesterday"},
        {"algo_id": "zen", "date": "1999-01-01"},
    ],
)
def test_debug_refuses_bad_requests_in_plain_words(client, payload):
    r = client.post("/algos/api/debug", json=payload)
    assert r.status_code == 400 and r.get_json()["message"]


def test_debug_says_when_a_day_cannot_be_replayed(client, monkeypatch, history):  # noqa: F811
    monkeypatch.setattr(lab, "load_history", lambda *a, **k: history)
    r = client.post("/algos/api/debug", json={"algo_id": "zen", "date": "2024-01-06"})
    assert r.status_code == 400 and "cannot be replayed" in r.get_json()["message"]


def test_explain_lists_real_decisions_and_is_private(app, client):
    dep = client.post(
        "/algos/api/deployments", json={"algo_id": "zen", "capital": 500000}
    ).get_json()["data"]
    algo_db.record_decision(
        dep["id"],
        "skip",
        "Volatile market.",
        regime_label="volatile",
        bias="neutral",
        confidence=0.9,
    )
    items = client.get(f"/algos/api/deployments/{dep['id']}/explain").get_json()["data"]
    assert items and items[0]["verdict"].startswith("Zen sat out")
    other = app.test_client()
    _login(other, OTHER)
    assert other.get(f"/algos/api/deployments/{dep['id']}/explain").status_code == 404


def test_readiness_shows_the_servers_address_and_what_is_missing(client, monkeypatch):
    from database import auth_db, master_contract_status_db
    from services.algos import netinfo

    monkeypatch.setattr(netinfo, "public_ip", lambda: "203.0.113.7")
    monkeypatch.setattr(auth_db, "get_api_key", lambda user: True)
    monkeypatch.setattr(auth_db, "get_auth_token", lambda user: None)
    monkeypatch.setattr(master_contract_status_db, "check_if_ready", lambda broker: True)
    with client.session_transaction() as s:
        s["broker"] = "upstox"
    data = client.get("/algos/api/readiness").get_json()["data"]
    steps = {s["id"]: s for s in data["steps"]}
    assert "203.0.113.7" in steps["static_ip"]["detail"]
    assert steps["broker"]["state"] == "todo" and data["ready_for_live"] is False


def test_event_days_can_be_listed_added_and_removed_over_http(client, monkeypatch, tmp_path):
    from services.algos import events

    monkeypatch.setattr(events, "PATH", tmp_path / "e.json")
    day = (datetime.now() + __import__("datetime").timedelta(days=10)).strftime("%Y-%m-%d")
    added = client.post("/algos/api/events", json={"date": day, "label": "Union Budget"})
    assert added.status_code == 201 and added.get_json()["data"][0]["label"] == "Union Budget"
    bad = client.post("/algos/api/events", json={"date": "soon", "label": "x"})
    assert bad.status_code == 400 and "like 2026-02-01" in bad.get_json()["message"]
    assert client.delete(f"/algos/api/events/{day}").get_json()["data"] == []
