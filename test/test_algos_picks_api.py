"""Tracked picks over HTTP: a pick records legs and prices, follows live prices and closes; no order anywhere."""

from datetime import datetime

import pytest
import pytz
from flask import Blueprint, Flask

from blueprints import algos
from limiter import limiter
from services.algos import pick_log, picker_inputs

CALL = {"kind": "CE", "strike": 23950.0, "side": "B", "qty": 1, "price": 100.0}


def fake_picker():
    return {
        "header": {
            "expiry": "09NOV26",
            "lot": 65,
            "spot": 23950.0,
            "dte": 5,
            "vix": 15.0,
            "regime": {"label": "calm", "bias": "neutral", "reasons": []},
            "research": {"expected_gap": {"gap_pct": 0.2, "links": []}},
        },
        "ranked": [
            {
                "id": "long_call",
                "name": "Long Call",
                "score": 61.5,
                "components": {"direction": 0.5},
                "priced_legs": [CALL],
                "capital_required": 6500.0,
                "stats": {"max_loss": 6500.0},
            }
        ],
        "blocked": [],
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(algos, "_custom_loaded", True)
    monkeypatch.setattr(algos, "_pick_log", pick_log.PickLog(tmp_path / "picks.jsonl"))
    monkeypatch.setattr(algos.runner, "_api_key", lambda user: "test-key")
    monkeypatch.setattr(algos, "_picker_data", lambda *a, **k: fake_picker())
    monkeypatch.setattr(
        picker_inputs, "live_mids", lambda api_key, expiry: {("CE", 23950.0): 130.0}
    )
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="picks-tests", PROPAGATE_EXCEPTIONS=True)
    app.register_blueprint(algos.algos_bp)
    auth = Blueprint("auth", __name__)
    auth.add_url_rule("/auth/login", "login", lambda: ("login", 200))
    app.register_blueprint(auth)
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
        s["user"] = "picks_user"
        s["login_time"] = datetime.now(pytz.timezone("Asia/Kolkata")).isoformat()
    return c


def test_tracking_a_strategy_records_its_legs_prices_and_the_conditions(client):
    reply = client.post("/algos/api/picks", json={"template_id": "long_call"})
    assert reply.status_code == 200
    pick = reply.get_json()["data"]
    assert pick["status"] == "open" and pick["fit"] == 61.5 and pick["lot"] == 65
    assert pick["legs"] == [CALL] and pick["conditions"]["regime"] == "calm"
    assert pick["conditions"]["expected_gap_pct"] == 0.2 and pick["max_loss"] == 6500.0


def test_a_strategy_that_is_not_in_the_list_cannot_be_tracked(client):
    reply = client.post("/algos/api/picks", json={"template_id": "short_straddle"})
    assert reply.status_code == 400 and "not available" in reply.get_json()["message"]


def test_the_list_marks_open_picks_with_live_prices_and_summarises_closed_ones(client):
    client.post("/algos/api/picks", json={"template_id": "long_call"})
    body = client.get("/algos/api/picks").get_json()["data"]
    assert body["picks"][0]["unrealized"] == 1950.0  # (130 - 100) * 65
    assert body["summary"]["open"] == 1 and body["summary"]["closed"] == 0
    assert "Too few" in body["summary"]["verdict"]


def test_closing_without_a_result_uses_the_live_price_and_closing_twice_is_refused(client):
    pick = client.post("/algos/api/picks", json={"template_id": "long_call"}).get_json()["data"]
    done = client.post(f"/algos/api/picks/{pick['id']}/close", json={})
    assert done.status_code == 200 and done.get_json()["data"]["pnl"] == 1950.0
    again = client.post(f"/algos/api/picks/{pick['id']}/close", json={})
    assert again.status_code == 400 and "already closed" in again.get_json()["message"]


def test_a_typed_result_is_used_and_a_junk_one_is_refused(client):
    pick = client.post("/algos/api/picks", json={"template_id": "long_call"}).get_json()["data"]
    assert (
        client.post(f"/algos/api/picks/{pick['id']}/close", json={"pnl": "lots"}).status_code == 400
    )
    ok = client.post(f"/algos/api/picks/{pick['id']}/close", json={"pnl": -1200})
    assert ok.get_json()["data"]["pnl"] == -1200.0


def test_with_no_live_prices_the_trader_is_asked_to_type_the_result(client, monkeypatch):
    pick = client.post("/algos/api/picks", json={"template_id": "long_call"}).get_json()["data"]
    monkeypatch.setattr(picker_inputs, "live_mids", lambda api_key, expiry: {})
    reply = client.post(f"/algos/api/picks/{pick['id']}/close", json={})
    assert reply.status_code == 400 and "type in its result" in reply.get_json()["message"]


def test_no_order_function_is_reachable_from_the_pick_endpoints():
    import inspect

    src = "".join(
        inspect.getsource(f) for f in (algos.picks_add, algos.picks_list, algos.picks_close)
    )
    for word in ("place_order", "placeorder", "basketorder", "smartorder"):
        assert word not in src.lower()


def test_mid_prices_prefer_the_bid_ask_middle_and_fall_back_to_the_last_price():
    chain = {
        ("CE", 100.0): {"bid": 9, "ask": 11, "ltp": 8},
        ("PE", 100.0): {"bid": 0, "ask": 0, "ltp": 7},
        ("CE", 200.0): {"bid": 0, "ask": 0, "ltp": 0},
    }
    mids = picker_inputs.mids_from_chain(chain)
    assert mids == {("CE", 100.0): 10.0, ("PE", 100.0): 7.0}
