"""The Lab endpoint: validation, caching, failures in plain words, caveats always attached."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
import pytz
from flask import Blueprint, Flask

from blueprints import algos
from limiter import limiter
from services.algos import lab
from services.algos.lab import History, HistoryUnavailable

USER = "lab_api_user"


def _frame(seed, level, vol, days=160):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=days)
    close = level * np.exp(np.cumsum(rng.normal(0, vol, days)))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, vol / 3, days))
    return pd.DataFrame({"Open": open_, "Close": close}, index=idx)


@pytest.fixture
def synthetic():
    return History(
        {
            "nifty": _frame(1, 22000, 0.006),
            "vix": _frame(2, 14, 0.03),
            "spx": _frame(3, 5000, 0.007),
            "ndx": _frame(4, 17000, 0.009),
            "crude": _frame(5, 80, 0.015),
            "dxy": _frame(6, 104, 0.003),
        }
    )


@pytest.fixture(autouse=True)
def stubs(monkeypatch, synthetic):
    monkeypatch.setattr(limiter, "enabled", False)
    calls = {"loads": 0}

    def fake_load():
        calls["loads"] += 1
        return synthetic

    monkeypatch.setattr(lab, "load_history", fake_load)
    algos._history_cache.clear()
    algos._lab_cache.clear()
    return calls


@pytest.fixture
def calls(stubs):
    return stubs


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="lab-tests", PROPAGATE_EXCEPTIONS=True)
    app.register_blueprint(algos.algos_bp)
    auth = Blueprint("auth", __name__)
    auth.add_url_rule("/auth/login", "login", lambda: ("login", 200))
    app.register_blueprint(auth)
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
        s["user"] = USER
        s["login_time"] = datetime.now(pytz.timezone("Asia/Kolkata")).isoformat()
    return c


def run(client, **body):
    body.setdefault("algo_id", "zen")
    return client.post("/algos/api/lab/run", json=body)


def test_a_run_returns_metrics_curve_yearly_and_the_caveats(client):
    r = run(client)
    assert r.status_code == 200
    d = r.get_json()["data"]
    assert d["algo_name"] == "Zen" and d["model"]["name"] == "conservative"
    assert d["metrics"]["trades"] == len(d["trades"]) or len(d["trades"]) == 100
    assert d["curve"] and all(len(p) == 2 for p in d["curve"])
    assert d["yearly"] and "year" in d["yearly"][0]
    assert len(d["caveats"]) >= 3 and any("not real fills" in c for c in d["caveats"])


def test_the_standard_model_warns_that_it_flatters_option_sellers(client):
    caveats = run(client, model="standard").get_json()["data"]["caveats"]
    assert any("flatters" in c for c in caveats)


def test_only_overnight_algos_carry_the_overnight_decay_warning(client):
    zen = run(client, algo_id="zen").get_json()["data"]["caveats"]
    gap = run(client, algo_id="morning_gap").get_json()["data"]["caveats"]
    assert any("decides the result for overnight algos" in c for c in zen)
    assert not any("decides the result" in c for c in gap)


def test_identical_requests_share_one_computation_and_one_download(client, calls):
    run(client)
    run(client)
    run(client, algo_id="calm_condor")
    assert calls["loads"] == 1


@pytest.mark.parametrize(
    "body",
    [
        {"algo_id": "nope"},
        {"model": "optimistic"},
        {"gated": "yes"},
        {"start": "last year"},
        {"start": 2023},
        {"end": "2999-01-01"},
        {"start": "2014-01-01"},
        {"start": "2024-06-01", "end": "2024-01-01"},
    ],
)
def test_bad_requests_are_refused_without_running_anything(client, calls, body):
    r = run(client, **body)
    assert r.status_code == 400 and calls["loads"] == 0


def test_when_history_cannot_be_downloaded_the_trader_is_told_what_to_do(client, monkeypatch):
    def down():
        raise HistoryUnavailable(
            "Could not download market history. Check your internet connection."
        )

    monkeypatch.setattr(lab, "load_history", down)
    r = run(client)
    assert r.status_code == 503
    message = r.get_json()["message"]
    assert "internet connection" in message and "Traceback" not in message


def test_an_unexpected_failure_is_a_plain_message_not_a_traceback(client, monkeypatch):
    monkeypatch.setattr(lab, "run_lab", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = run(client)
    assert r.status_code == 500
    message = r.get_json()["message"]
    assert "boom" not in message and "RuntimeError" not in message and "Try again" in message


def test_the_date_range_is_applied(client):
    d = run(client, start="2024-03-01", end="2024-04-30").get_json()["data"]
    assert d["start"] == "2024-03-01" and d["end"] == "2024-04-30"
    assert all("2024-03-01" <= t["date"] <= "2024-04-30" for t in d["trades"])


def test_logged_out_callers_get_nothing():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="x")
    app.register_blueprint(algos.algos_bp)
    auth = Blueprint("auth", __name__)
    auth.add_url_rule("/auth/login", "login", lambda: ("login", 200))
    app.register_blueprint(auth)
    r = app.test_client().post("/algos/api/lab/run", json={"algo_id": "zen"})
    assert r.status_code in (401, 302)


def test_downsample_keeps_the_first_and_last_points():
    curve = [[f"d{i}", float(i)] for i in range(1000)]
    out = lab.downsample(curve, 50)
    assert len(out) == 50 and out[0] == curve[0] and out[-1] == curve[-1]
    assert lab.downsample(curve[:10], 50) == curve[:10]
