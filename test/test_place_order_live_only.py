"""The optional live_only field: an order that carries it is refused when analyzer mode is on.

The mirror of sandbox_only. A live executor that has been told to place a real order must never have it
quietly sent to the sandbox, where it would report success while nothing reaches the broker.
"""

import pytest

import restx_api  # noqa: F401, I001  (loads the package first; avoids a circular import)
from services import place_order_service as svc  # noqa: E402
from services import sandbox_service  # noqa: E402

ORDER = {
    "strategy": "ATM200-live",
    "exchange": "NFO",
    "symbol": "NIFTY23NOV2625450CE",
    "action": "SELL",
    "quantity": 65,
    "pricetype": "LIMIT",
    "product": "NRML",
    "price": 209.0,
    "live_only": True,
}


def call(**over):
    data = {**ORDER, **over}
    return svc.place_order_with_auth(
        dict(data), "token", "upstox", {**data, "apikey": "k"}, emit_event=False
    )


def test_a_live_only_order_is_refused_when_analyzer_mode_is_on_and_nothing_is_placed(monkeypatch):
    monkeypatch.setattr(svc, "get_analyze_mode", lambda: True)
    placed = []
    monkeypatch.setattr(
        sandbox_service,
        "sandbox_place_order",
        lambda *a, **k: placed.append(1) or (True, {"status": "success", "orderid": "S1"}, 200),
    )
    ok, body, status = call()
    assert (ok, status) == (False, 403)
    assert "live only" in body["message"] and "nothing was sent to the broker" in body["message"]
    assert placed == []  # the sandbox never saw it, so it cannot report a false success


def test_the_mode_is_read_once_for_both_the_refusal_and_the_routing(monkeypatch):
    reads = []

    def flip():
        reads.append(1)
        return len(reads) == 1  # analyzer on for the first read, off for any later one

    monkeypatch.setattr(svc, "get_analyze_mode", flip)
    ok, _body, status = call()
    assert (ok, status) == (False, 403)
    assert len(reads) == 1


def test_a_live_only_order_in_live_mode_reaches_the_broker_without_the_flag(monkeypatch):
    monkeypatch.setattr(svc, "get_analyze_mode", lambda: False)
    seen = {}

    class Fake:
        @staticmethod
        def place_order_api(data, auth):
            seen["order"] = data
            return type("R", (), {"status": 200})(), {"status": "success", "orderid": "B1"}, "B1"

    monkeypatch.setattr(svc.importlib, "import_module", lambda name: Fake)
    ok, body, status = call()
    assert (ok, status) == (True, 200) and body["orderid"] == "B1"
    assert "live_only" not in seen["order"]  # the flag is not passed on to the broker


def test_an_order_without_the_flag_is_routed_exactly_as_before(monkeypatch):
    monkeypatch.setattr(svc, "get_analyze_mode", lambda: True)
    called = []
    monkeypatch.setattr(
        "services.sandbox_service.sandbox_place_order",
        lambda *a, **k: called.append(1) or (True, {"status": "success", "orderid": "S2"}, 200),
    )
    ok, _body, status = call(live_only=False)
    assert (ok, status) == (True, 200) and called == [1]


def test_a_sandbox_only_order_still_behaves_as_before(monkeypatch):
    monkeypatch.setattr(svc, "get_analyze_mode", lambda: False)

    def boom(*a, **k):
        raise AssertionError("an order reached the broker")

    monkeypatch.setattr(svc.importlib, "import_module", boom)
    ok, _body, status = call(live_only=False, sandbox_only=True)
    assert (ok, status) == (False, 403)


@pytest.mark.parametrize("flag", ["sandbox_only", "live_only"])
def test_the_schema_accepts_both_flags_and_defaults_them_to_false(flag):
    from restx_api.schemas import OrderSchema

    loaded = OrderSchema().load(
        {
            "apikey": "k",
            "strategy": "s",
            "exchange": "NFO",
            "symbol": "NIFTY23NOV2625450CE",
            "action": "BUY",
            "quantity": 65,
        }
    )
    assert loaded[flag] is False
