"""Registry over HTTP: the register can be read and written, and nothing here runs or promotes."""

from datetime import datetime

import pytest
import pytz
from flask import Blueprint, Flask

from blueprints import algos
from limiter import limiter
from services.algos import registry as reg


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


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(algos, "REGISTRY_DIR", tmp_path)
    monkeypatch.setattr(algos, "_custom_loaded", True)  # no database in these tests
    monkeypatch.setattr(
        algos, "datetime", type("D", (), {"now": staticmethod(lambda: datetime(2027, 1, 4, 10, 0))})
    )
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="registry-tests", PROPAGATE_EXCEPTIONS=True)
    app.register_blueprint(algos.algos_bp)
    auth = Blueprint("auth", __name__)
    auth.add_url_rule("/auth/login", "login", lambda: ("login", 200))
    app.register_blueprint(auth)
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
        s["user"] = "registry_user"
        s["login_time"] = datetime.now(pytz.timezone("Asia/Kolkata")).isoformat()
    return c


def test_the_register_starts_with_the_seeded_count_and_the_next_free_month(client):
    body = client.get("/algos/api/registry").get_json()["data"]
    assert body["trial_count"] == reg.SEED_TRIALS and body["registrations"] == []
    assert body["next_free_month"] == "2027-01"
    assert "2026-11" in body["months_used"] and "kill_rule" in body["fields"]


def test_registering_returns_201_and_the_count_moves(client):
    response = client.post("/algos/api/registry", json=draft())
    assert response.status_code == 201
    assert response.get_json()["data"]["trial_numbers"] == [320, 320]
    body = client.get("/algos/api/registry").get_json()["data"]
    assert body["trial_count"] == 320 and body["registrations"][0]["intact"] is True
    assert body["next_free_month"] == "2027-02"


def test_an_incomplete_idea_is_a_400_with_words_a_trader_can_act_on(client):
    response = client.post("/algos/api/registry", json=draft(kill_rule=""))
    assert response.status_code == 400
    assert "kill rule" in response.get_json()["message"]


def test_a_second_idea_in_the_same_month_is_a_400(client):
    client.post("/algos/api/registry", json=draft())
    again = client.post("/algos/api/registry", json=draft(name="Another idea"))
    assert again.status_code == 400 and "2027-02" in again.get_json()["message"]


def test_there_is_no_endpoint_to_run_edit_or_promote_a_registration(client):
    first = client.post("/algos/api/registry", json=draft()).get_json()["data"]["id"]
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(f"/algos/api/registry/{first}").status_code in (404, 405)
    assert client.post(f"/algos/api/registry/{first}/run", json={}).status_code == 404


def test_a_non_object_body_is_a_400(client):
    assert client.post("/algos/api/registry", json=[1, 2]).status_code == 400


def test_the_forward_list_reads_the_nightly_reports_and_is_empty_without_them(
    client, tmp_path, monkeypatch
):
    import json

    reports = tmp_path / "reports"  # not the register folder: that one only holds registrations
    reports.mkdir()
    monkeypatch.setenv("ALGO_FORWARD_S3N_REPORT", str(reports / "none.json"))
    monkeypatch.setenv("ALGO_FORWARD_EOD_DIR", str(reports / "eod"))
    assert client.get("/algos/api/forward").get_json()["data"] == []
    (reports / "s3n.json").write_text(
        json.dumps({"ledgers": {"L1": {"completed": 3, "realistic_net": 1200,
                                       "status": {"state": "running", "verdict": None, "trades_to_go": 23}}}}),
        encoding="utf-8",
    )  # fmt: skip
    monkeypatch.setenv("ALGO_FORWARD_S3N_REPORT", str(reports / "s3n.json"))
    row = client.get("/algos/api/forward").get_json()["data"][0]
    assert (
        row["state"] == "running"
        and row["completed"] == 3
        and row["trades_to_go"] == 23
        and row["net"] == 1200
    )
