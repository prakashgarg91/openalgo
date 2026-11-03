"""Upstox order writes go through the static-IP proxy when one is configured, and only those."""

import httpx
import pytest

from utils import order_proxy


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("UPSTOX_ORDER_PROXY_URL", raising=False)
    order_proxy.close()
    yield
    order_proxy.close()


def test_without_a_proxy_the_shared_client_is_used():
    from utils.httpx_client import get_httpx_client

    assert order_proxy.proxy_url() is None
    assert order_proxy.order_client() is get_httpx_client()


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_setting_means_no_proxy(monkeypatch, value):
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_URL", value)
    assert order_proxy.proxy_url() is None


def test_a_proxy_gives_its_own_client_that_is_reused(monkeypatch):
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_URL", "http://user:secret@proxy.example:443")
    first = order_proxy.order_client()
    assert isinstance(first, httpx.Client)
    assert first is order_proxy.order_client()
    from utils.httpx_client import get_httpx_client

    assert first is not get_httpx_client()


def test_a_malformed_proxy_is_refused_instead_of_sending_orders_direct(monkeypatch):
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_URL", "proxy.example:443")
    with pytest.raises(order_proxy.OrderProxyError) as err:
        order_proxy.order_client()
    assert "secret" not in str(err.value)


def test_the_label_never_shows_the_login(monkeypatch):
    monkeypatch.setenv("UPSTOX_ORDER_PROXY_URL", "http://user:secret@proxy.example:443")
    label = order_proxy.describe()
    assert "proxy.example" in label and "secret" not in label and "user" not in label


def test_the_order_and_gtt_writes_use_the_order_client(monkeypatch):
    """The plugin must ask order_proxy for the client on every write path, never the shared one."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "broker" / "upstox" / "api"
    order_src = (root / "order_api.py").read_text(encoding="utf-8")
    gtt_src = (root / "gtt_api.py").read_text(encoding="utf-8")
    assert "order_proxy" in order_src and "order_proxy" in gtt_src
    # the place call and the hft-hosted calls pick the client through the helper
    assert "client = order_client()" in order_src
    assert gtt_src.count("order_client()") >= 3  # place, modify, cancel
