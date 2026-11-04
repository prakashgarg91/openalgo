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


def test_static_ip_step_names_the_servers_address_when_known():
    detail = evaluate(_facts(public_ip="203.0.113.7"))["steps"][-1]["detail"]
    assert "203.0.113.7" in detail and "exactly this address" in detail


def test_static_ip_step_degrades_to_plain_words_when_the_address_is_unknown():
    out = evaluate(_facts())
    detail = out["steps"][-1]["detail"]
    assert "could not look its own address up" in detail and out["steps"][-1]["state"] == "confirm"


from datetime import date  # noqa: E402

TODAY = date(2026, 11, 4)


def _proxy(**kw):
    base = {
        "proxy_host": "dc-mum-007.staticip.in:443",
        "proxy_outbound_ip": "151.245.182.73",
        "proxy_registered_ip": "151.245.182.73",
        "proxy_valid_until": date(2026, 12, 31),
        "today": TODAY,
    }
    base.update(kw)
    return _facts(**base)


def _step(out):
    return out["steps"][-1]


def test_without_a_proxy_nothing_changes():
    out = evaluate(_facts())
    assert _step(out)["id"] == "static_ip"
    assert "order_proxy" not in {s["id"] for s in out["steps"]}


def test_a_working_proxy_replaces_the_home_address_step_and_names_the_exit_address():
    out = evaluate(_proxy(public_ip="103.87.57.14"))
    step = _step(out)
    assert step["id"] == "order_proxy" and step["state"] == "confirm"
    assert "151.245.182.73" in step["detail"] and "103.87.57.14" not in step["detail"]
    assert "exactly this address" in step["detail"]
    assert out["ready_for_live"]


def test_a_proxy_that_does_not_answer_blocks_live():
    out = evaluate(_proxy(proxy_outbound_ip=None))
    assert _step(out)["state"] == "todo" and not out["ready_for_live"]
    assert "did not answer" in _step(out)["detail"]


def test_an_exit_address_that_differs_from_the_recorded_one_blocks_live():
    out = evaluate(_proxy(proxy_outbound_ip="151.245.182.99"))
    step = _step(out)
    assert (
        step["state"] == "todo"
        and "151.245.182.99" in step["detail"]
        and "151.245.182.73" in step["detail"]
    )


def test_the_plan_running_out_is_warned_then_blocks():
    soon = _step(evaluate(_proxy(proxy_valid_until=date(2026, 11, 11))))
    assert (
        soon["state"] == "confirm"
        and "7 days" in soon["detail"]
        and "renew" in soon["detail"].lower()
    )
    last = _step(evaluate(_proxy(proxy_valid_until=date(2026, 11, 6))))
    assert last["state"] == "todo" and "2 days" in last["detail"]
    gone = evaluate(_proxy(proxy_valid_until=date(2026, 11, 3)))
    assert (
        _step(gone)["state"] == "todo"
        and "ended" in _step(gone)["detail"]
        and not gone["ready_for_live"]
    )


def test_an_unrecorded_expiry_says_so_instead_of_guessing():
    step = _step(evaluate(_proxy(proxy_valid_until=None)))
    assert step["state"] == "confirm" and "expiry date" in step["detail"].lower()
