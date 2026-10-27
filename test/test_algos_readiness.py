from services.algos.readiness import Facts, evaluate


def _facts(**kw):
    base = {
        "broker": "upstox",
        "has_api_key": True,
        "broker_logged_in": True,
        "master_contract_ready": True,
    }
    base.update(kw)
    return Facts(**base)


def test_all_done_is_ready_but_static_ip_stays_a_confirmation():
    out = evaluate(_facts())
    assert out["ready_for_live"] and out["next"] is None
    assert out["steps"][-1]["id"] == "static_ip" and out["steps"][-1]["state"] == "confirm"


def test_missing_key_blocks_both_and_points_at_the_page():
    out = evaluate(_facts(has_api_key=False))
    assert not out["ready_for_sandbox"] and not out["ready_for_live"]
    assert out["next"] == "api_key" and out["steps"][0]["path"] == "/apikey"


def test_expired_login_blocks_live_only():
    out = evaluate(_facts(broker_logged_in=False))
    assert out["ready_for_sandbox"] and not out["ready_for_live"]
    assert out["next"] == "broker"
    assert "expire" in out["steps"][1]["detail"]


def test_no_broker_name_reads_naturally():
    out = evaluate(_facts(broker=None, broker_logged_in=False))
    assert out["steps"][1]["label"] == "Your Broker login for today"


def test_wording_has_no_internal_terms():
    text = " ".join(s["detail"] + s["label"] for s in evaluate(_facts(has_api_key=False))["steps"])
    for bad in ("HTTP", "token", "403", "armed"):
        assert bad not in text
