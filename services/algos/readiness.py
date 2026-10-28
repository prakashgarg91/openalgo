"""Is this installation ready to place a Live order? Pure: the caller gathers the facts.

Each step says what is wrong in a trader's words and what to do next. The static
IP cannot be checked from here (only the broker knows which address it accepts), so
that step is always the trader's own confirmation and is reported as such.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Facts:
    broker: str | None
    has_api_key: bool
    broker_logged_in: bool
    master_contract_ready: bool
    public_ip: str | None = None


@dataclass(frozen=True)
class Step:
    id: str
    label: str
    state: str  # "done" | "todo" | "confirm"
    detail: str
    path: str | None = None


def _broker_name(broker: str | None) -> str:
    return (broker or "your broker").replace("_", " ").title()


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
        Step(
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
