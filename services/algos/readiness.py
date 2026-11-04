"""Is this installation ready to place a Live order? Pure: the caller gathers the facts.

Each step says what is wrong in a trader's words and what to do next. The static
IP cannot be checked from here (only the broker knows which address it accepts), so
that step is always the trader's own confirmation and is reported as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Facts:
    broker: str | None
    has_api_key: bool
    broker_logged_in: bool
    master_contract_ready: bool
    public_ip: str | None = None
    # A static-IP proxy for order writes (UPSTOX_ORDER_PROXY_URL). When set, the proxy's exit address is the one
    # the broker sees, so it replaces this server's own address in the static IP step.
    proxy_host: str | None = None
    proxy_outbound_ip: str | None = None
    proxy_registered_ip: str | None = None
    proxy_valid_until: date | None = None
    today: date | None = None


@dataclass(frozen=True)
class Step:
    id: str
    label: str
    state: str  # "done" | "todo" | "confirm"
    detail: str
    path: str | None = None


def _broker_name(broker: str | None) -> str:
    return (broker or "your broker").replace("_", " ").title()


def _proxy_step(facts: Facts) -> Step:
    """The static IP step when orders leave through a rented proxy: its exit address, its plan, its expiry."""
    host, exit_ip, recorded = facts.proxy_host, facts.proxy_outbound_ip, facts.proxy_registered_ip
    label = "Static IP proxy for orders"
    if not exit_ip:
        return Step(
            "order_proxy",
            label,
            "todo",
            f"Orders are set to go through your proxy ({host}), but it did not answer. Check that the plan "
            "is active and that its login in the settings file is right, then restart OpenAlgo.",
        )
    if recorded and recorded != exit_ip:
        return Step(
            "order_proxy",
            label,
            "todo",
            f"The proxy exits from {exit_ip}, but the address you recorded as registered is {recorded}. "
            f"Register {exit_ip} with your broker (it can be changed once a week), or fix the recorded "
            "address if it is a typo.",
        )
    days = None
    if facts.proxy_valid_until and facts.today:
        days = (facts.proxy_valid_until - facts.today).days
    if days is not None and days < 0:
        return Step(
            "order_proxy",
            label,
            "todo",
            f"Your proxy plan ended on {facts.proxy_valid_until:%d %b %Y}. Renew it, or orders will not go through.",
        )
    detail = (
        f"Orders leave from {exit_ip} (through {host}). Your broker must have exactly this address "
        "registered, or orders are rejected."
    )
    state = "confirm"
    if days is None:
        detail += (
            " The plan's expiry date is not recorded, so nothing will warn you before it ends."
        )
    elif days <= 2:
        state = "todo"
        detail += f" The plan ends in {days} days. Renew it before trading."
    elif days <= 7:
        detail += f" The plan ends in {days} days ({facts.proxy_valid_until:%d %b %Y}). Renew it before then."
    else:
        detail += f" The plan runs to {facts.proxy_valid_until:%d %b %Y}."
    return Step("order_proxy", label, state, detail)


def evaluate(facts: Facts) -> dict:
    name = _broker_name(facts.broker)
    steps = [
        Step(
            "api_key",
            "OpenAlgo API key",
            "done" if facts.has_api_key else "todo",
            "Created." if facts.has_api_key else "Create your API key; every algo needs it.",
            None if facts.has_api_key else "/apikey",
        ),
        Step(
            "broker",
            f"{name} login for today",
            "done" if facts.broker_logged_in else "todo",
            "Logged in for today."
            if facts.broker_logged_in
            else "Log in to your broker again. Broker logins expire every morning.",
            None if facts.broker_logged_in else "/broker",
        ),
        Step(
            "master_contract",
            "Instrument list downloaded",
            "done" if facts.master_contract_ready else "todo",
            "Ready."
            if facts.master_contract_ready
            else "The instrument list is not ready yet. It downloads after you log in; if this stays, open the page and download it again.",
            None if facts.master_contract_ready else "/master-contract",
        ),
        _proxy_step(facts)
        if facts.proxy_host
        else Step(
            "static_ip",
            "Static IP registered with your broker",
            "confirm",
            (
                f"This server reaches the internet from {facts.public_ip}. Your broker must have "
                "exactly this address on its allowed list, or orders are rejected. Check it in "
                "your broker's developer settings."
                if facts.public_ip
                else "Orders are rejected unless your broker has this server's address on its "
                "allowed list. OpenAlgo could not look its own address up just now; check it in "
                "your broker's developer settings."
            ),
        ),
    ]
    blocking = [s for s in steps if s.state == "todo"]
    return {
        "steps": [s.__dict__ for s in steps],
        "ready_for_sandbox": facts.has_api_key,
        "ready_for_live": not blocking,
        "next": blocking[0].id if blocking else None,
    }
