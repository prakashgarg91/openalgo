"""Route Upstox order writes through a static-IP proxy, and nothing else.

Since 1 April 2026 Upstox refuses order calls (place, modify, cancel, GTT) that do not come from a registered
static IP. A home connection changes address, so the trader rents a proxy with a fixed one. Only the order
writes need it: quotes, candles, the order book and funds keep using the ordinary client.

Set ``UPSTOX_ORDER_PROXY_URL`` in ``.env`` to ``http://user:password@host:port``. Unset, or blank, orders go out
directly exactly as before. A value that is set but unusable raises instead of falling back to a direct send,
because a direct order would be refused by Upstox and would also hide that the proxy is misconfigured.
"""

import os
from urllib.parse import urlsplit

import httpx

from utils.lazy import LazyInit
from utils.logging import get_logger

logger = get_logger(__name__)

ENV_NAME = "UPSTOX_ORDER_PROXY_URL"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class OrderProxyError(RuntimeError):
    """The order proxy is configured but cannot be used. The message never carries the login."""


def proxy_url() -> str | None:
    value = os.getenv(ENV_NAME, "").strip().strip("'\"")
    return value or None


def _check(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or not parts.port:
        raise OrderProxyError(
            f"{ENV_NAME} must look like http://user:password@host:port. Fix it in .env and restart."
        )


def describe() -> str:
    """Host and port for logs and screens, never the login."""
    url = proxy_url()
    if not url:
        return "direct (no order proxy)"
    parts = urlsplit(url)
    return f"{parts.hostname}:{parts.port}" if parts.hostname and parts.port else "unusable setting"


def _build() -> httpx.Client:
    url = proxy_url()
    if not url:
        raise OrderProxyError("no order proxy configured")
    _check(url)
    from utils.httpx_client import _BrokerClient

    return _BrokerClient(
        proxy=url,
        http2=False,
        timeout=_TIMEOUT,
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10, keepalive_expiry=30.0),
    )


_client = LazyInit(_build, name="order-proxy-client")


def order_client() -> httpx.Client:
    """The client for an Upstox order write: the proxy's when one is set, else the shared client."""
    if not proxy_url():
        from utils.httpx_client import get_httpx_client

        return get_httpx_client()
    _check(proxy_url())
    return _client.get()


def close() -> None:
    """Close the proxy client, if one was built (shutdown and tests)."""
    _client.reset(close=lambda client: client.close())
