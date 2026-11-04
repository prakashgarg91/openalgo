import pytest

from services.algos import netinfo


@pytest.fixture(autouse=True)
def clean():
    netinfo._found.clear()
    netinfo._failed.clear()
    yield
    netinfo._found.clear()
    netinfo._failed.clear()


class Resp:
    def __init__(self, text, fail=False):
        self.text, self._fail = text, fail

    def raise_for_status(self):
        if self._fail:
            raise RuntimeError("boom")


class Client:
    def __init__(self, resp):
        self.resp, self.calls = resp, 0

    def get(self, url, timeout):
        self.calls += 1
        assert timeout <= 5
        return self.resp


@pytest.mark.parametrize("good", ["203.0.113.7", " 203.0.113.7\n", "2001:db8::1"])
def test_only_a_real_address_is_accepted(good):
    assert netinfo.parse(good) == good.strip()


@pytest.mark.parametrize("bad", ["", "<html>", "999.1.1.1", "1.2.3.4; rm -rf /", "x" * 500])
def test_anything_else_is_dropped(bad):
    assert netinfo.parse(bad) is None


def test_the_answer_is_kept_so_pages_do_not_each_make_a_request(monkeypatch):
    client = Client(Resp("203.0.113.7"))
    monkeypatch.setattr(netinfo, "get_httpx_client", lambda: client)
    assert netinfo.public_ip() == "203.0.113.7" == netinfo.public_ip()
    assert client.calls == 1


def test_a_failure_is_remembered_briefly_and_never_raises(monkeypatch):
    client = Client(Resp("", fail=True))
    monkeypatch.setattr(netinfo, "get_httpx_client", lambda: client)
    assert netinfo.public_ip() is None and netinfo.public_ip() is None
    assert client.calls == 1


def test_a_garbled_answer_is_treated_as_a_failure(monkeypatch):
    client = Client(Resp("<html>blocked</html>"))
    monkeypatch.setattr(netinfo, "get_httpx_client", lambda: client)
    assert netinfo.public_ip() is None


def _clear_proxy():
    netinfo._proxy_found.clear()
    netinfo._proxy_failed.clear()


def test_without_a_proxy_there_are_no_proxy_facts_and_no_lookup(monkeypatch):
    from datetime import date

    monkeypatch.delenv("UPSTOX_ORDER_PROXY_URL", raising=False)
    assert netinfo.proxy_facts(date(2026, 11, 4)) == {}
    assert netinfo.proxy_outbound_ip() is None


def test_the_proxy_exit_address_is_asked_through_the_order_client_and_remembered(monkeypatch):
    from utils import order_proxy

    _clear_proxy()
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_URL", "http://u:p@proxy.example:443")
    client = Client(Resp("151.245.182.73"))
    monkeypatch.setattr(order_proxy, "order_client", lambda: client)
    assert netinfo.proxy_outbound_ip() == "151.245.182.73"
    assert netinfo.proxy_outbound_ip() == "151.245.182.73"
    assert client.calls == 1
    _clear_proxy()


def test_a_failing_proxy_is_remembered_for_two_minutes_so_pages_do_not_wait(monkeypatch):
    from utils import order_proxy

    _clear_proxy()
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_URL", "http://u:p@proxy.example:443")
    client = Client(Resp("", fail=True))
    monkeypatch.setattr(order_proxy, "order_client", lambda: client)
    assert netinfo.proxy_outbound_ip() is None
    assert netinfo.proxy_outbound_ip() is None
    assert client.calls == 1
    _clear_proxy()


def test_the_facts_carry_the_recorded_address_and_expiry_but_never_the_login(monkeypatch):
    from datetime import date

    from utils import order_proxy

    _clear_proxy()
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_URL", "http://user:secret@proxy.example:443")
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_REGISTERED_IP", "151.245.182.73")
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_VALID_UNTIL", "2026-11-11")
    monkeypatch.setattr(order_proxy, "order_client", lambda: Client(Resp("151.245.182.73")))
    facts = netinfo.proxy_facts(date(2026, 11, 4))
    assert facts["proxy_host"] == "proxy.example:443"
    assert facts["proxy_registered_ip"] == "151.245.182.73"
    assert facts["proxy_valid_until"] == date(2026, 11, 11)
    assert "secret" not in repr(facts) and "user" not in repr(facts)
    _clear_proxy()


def test_a_badly_written_expiry_is_treated_as_unrecorded(monkeypatch):
    from datetime import date

    from utils import order_proxy

    _clear_proxy()
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_URL", "http://u:p@proxy.example:443")
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_VALID_UNTIL", "11-11-2026")
    monkeypatch.setattr(order_proxy, "order_client", lambda: Client(Resp("151.245.182.73")))
    assert netinfo.proxy_facts(date(2026, 11, 4))["proxy_valid_until"] is None
    _clear_proxy()
