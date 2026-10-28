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
