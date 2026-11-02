"""The optional sandbox_only field: an order that carries it is refused unless analyzer mode is on."""

import pytest

import restx_api  # noqa: F401, I001  (loads the package first; avoids a circular import)
from services import place_order_service as svc  # noqa: E402
from services import sandbox_service  # noqa: E402

ORDER = {
    "strategy": "S3n-sandbox",
    "exchange": "NFO",
    "symbol": "NIFTY10NOV2625000CE",
    "action": "SELL",
    "quantity": 65,
    "pricetype": "LIMIT",
    "product": "NRML",
    "price": 20.0,
    "sandbox_only": True,
}


def call(**over):
    data = {**ORDER, **over}
    return svc.place_order_with_auth(
        dict(data), "token", "upstox", {**data, "apikey": "k"}, emit_event=False
    )


@pytest.fixture
def no_broker(monkeypatch):
    """Fail the test if anything tries to reach a broker module."""

    def boom(*a, **k):
        raise AssertionError("an order reached the broker")

    monkeypatch.setattr(svc.importlib, "import_module", boom)


def test_a_sandbox_only_order_is_refused_when_analyzer_mode_is_off_and_nothing_reaches_the_broker(
    monkeypatch, no_broker
):
    monkeypatch.setattr(svc, "get_analyze_mode", lambda: False)
    ok, body, status = call()
    assert (ok, status) == (False, 403)
    assert "sandbox only" in body["message"] and "nothing was sent to the broker" in body["message"]


def test_the_mode_is_read_once_so_a_switch_in_between_cannot_split_the_decision(
    monkeypatch, no_broker
):
    reads = []

    def flip():
        reads.append(1)
        return len(reads) == 1  # analyzer on for the first read, off for any later one

    monkeypatch.setattr(svc, "get_analyze_mode", flip)
    seen = {}

    def fake_sandbox(order_data, api_key, original_data, prefetched_quote=None):
        seen["order"] = order_data
        return True, {"status": "success", "orderid": "S1"}, 200

    monkeypatch.setattr(sandbox_service, "sandbox_place_order", fake_sandbox)
    ok, body, status = call()
    assert (ok, status) == (True, 200) and body["orderid"] == "S1"
    assert len(reads) == 1  # one read decided both the refusal check and the routing
    assert "sandbox_only" not in seen["order"]  # the flag is not passed on


def test_an_order_without_the_flag_is_routed_exactly_as_before(monkeypatch):
    monkeypatch.setattr(svc, "get_analyze_mode", lambda: True)
    called = []
    monkeypatch.setattr(
        "services.sandbox_service.sandbox_place_order",
        lambda *a, **k: called.append(1) or (True, {"status": "success", "orderid": "S2"}, 200),
    )
    ok, _body, status = call(sandbox_only=False)
    assert (ok, status) == (True, 200) and called == [1]
