"""The address this server reaches the internet from, so it can be compared with the broker's list.

Brokers accept orders only from an address registered with them. The server cannot read
that list, but it can say which address it is calling out from. One small request to a
public "what is my address" service answers it; the result is kept for ten minutes, and
a failure is remembered for two so a blocked network does not slow every page load.
"""

from __future__ import annotations

import ipaddress

from utils.httpx_client import get_httpx_client
from utils.logging import get_logger
from utils.thread_safe_cache import LockedTTLCache

logger = get_logger(__name__)

URL = "https://api.ipify.org"
TIMEOUT = 4.0
_found = LockedTTLCache(maxsize=1, ttl=600)
_failed = LockedTTLCache(maxsize=1, ttl=120)


def parse(text: str) -> str | None:
    """A valid address from the service's answer, or None. Nothing else is ever shown."""
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        return None


def public_ip() -> str | None:
    if _found.get("ip"):
        return _found.get("ip")
    if _failed.get("failed"):
        return None
    try:
        response = get_httpx_client().get(URL, timeout=TIMEOUT)
        response.raise_for_status()
        address = parse(response.text)
    except Exception:
        logger.warning("Could not look up this server's public address")
        address = None
    if address:
        _found["ip"] = address
    else:
        _failed["failed"] = True
    return address


_proxy_found = LockedTTLCache(maxsize=1, ttl=600)
_proxy_failed = LockedTTLCache(maxsize=1, ttl=120)


def proxy_outbound_ip() -> str | None:
    """The address Upstox sees for order writes: asked through the same proxy those orders use."""
    from utils import order_proxy

    if not order_proxy.proxy_url():
        return None
    if _proxy_found.get("ip"):
        return _proxy_found.get("ip")
    if _proxy_failed.get("failed"):
        return None
    try:
        response = order_proxy.order_client().get(URL, timeout=TIMEOUT)
        response.raise_for_status()
        address = parse(response.text)
    except Exception:
        logger.warning("Could not look up the order proxy's exit address")
        address = None
    if address:
        _proxy_found["ip"] = address
    else:
        _proxy_failed["failed"] = True
    return address


def proxy_facts(today) -> dict:
    """The proxy fields of the readiness facts. Empty when no proxy is set, so nothing else changes."""
    import os
    from datetime import date

    from utils import order_proxy

    if not order_proxy.proxy_url():
        return {}
    try:
        valid_until = date.fromisoformat(
            os.getenv("UPSTOX_ORDER_PROXY_VALID_UNTIL", "").strip().strip("'\"")
        )
    except ValueError:
        valid_until = None
    registered = os.getenv("UPSTOX_ORDER_PROXY_REGISTERED_IP", "").strip().strip("'\"") or None
    return {
        "proxy_host": order_proxy.describe(),
        "proxy_outbound_ip": proxy_outbound_ip(),
        "proxy_registered_ip": registered,
        "proxy_valid_until": valid_until,
        "today": today,
    }
