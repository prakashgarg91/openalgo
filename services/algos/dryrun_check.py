"""Is tomorrow's sandbox bot dry run ready? Pure: the caller gathers the facts.

This module performs no I/O, reads no clock and writes no logs. The caller
collects a Facts snapshot and receives plain rows back for display.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Facts:
    app_up: bool  # OpenAlgo answered
    key_set: bool  # OPENALGO_API_KEY is set (never the value)
    mode: str | None  # "analyze", "live" or None if unknown
    quote_ok: bool  # a Nifty quote with a price came back, so the broker session works
    today: date
    expiry: date | None  # nearest Nifty weekly expiry
    entry_day: date | None  # the session the bot enters, two sessions before expiry
    lot_qty: int | None  # quantity the bot would send
    legs: str  # "two_sided" | "none" | "unknown"  (bid and ask on both options)
    market_open: bool
    tasks: dict[
        str, str | None
    ]  # scheduled task name -> its next run text, None if the task is missing


REQUIRED_TASKS = ("OpenAlgo bid-ask 1015", "OpenAlgo option capture")
EXPECTED_LOT = 65


def evaluate(facts: Facts) -> list[tuple[str, str, str]]:
    """Return (level, check, message) rows. level is "ok", "warn" or "fail"."""
    rows: list[tuple[str, str, str]] = []

    if not facts.app_up:
        rows.append(
            ("fail", "OpenAlgo", "OpenAlgo is not answering. Start it with Start-OpenAlgo.bat.")
        )
        return rows
    rows.append(("ok", "OpenAlgo", "OpenAlgo is running."))

    if not facts.key_set:
        rows.append(("fail", "API key", "OPENALGO_API_KEY is not set for this Windows user."))
        return rows
    rows.append(("ok", "API key", "Set."))

    if facts.mode == "analyze":
        rows.append(("ok", "Mode", "Analyze (sandbox) mode is on."))
    elif facts.mode == "live":
        rows.append(
            ("fail", "Mode", "OpenAlgo is in Live mode. Switch to Analyze before the bot runs.")
        )
    else:
        rows.append(
            (
                "warn",
                "Mode",
                "Could not tell which mode is on. Check the top bar shows Analyze Mode.",
            )
        )

    if facts.quote_ok:
        rows.append(("ok", "Broker session", "Upstox is connected and prices are coming in."))
    else:
        rows.append(
            (
                "fail",
                "Broker session",
                "No Nifty price came back. Sign in to Upstox again (the login expires every morning).",
            )
        )

    if facts.expiry is None:
        rows.append(("fail", "Expiry", "No Nifty expiry found. Download the master contract."))
    else:
        rows.append(("ok", "Expiry", f"Nearest weekly expiry is {facts.expiry:%a %d %b %Y}."))

    if facts.entry_day is None:
        rows.append(("warn", "Entry day", "Could not work out the entry day."))
    elif facts.entry_day == facts.today:
        rows.append(("ok", "Entry day", "Today is the entry session."))
    elif facts.entry_day > facts.today:
        days = (facts.entry_day - facts.today).days
        rows.append(
            (
                "ok",
                "Entry day",
                f"The bot enters on {facts.entry_day:%a %d %b}, in {days} day(s).",
            )
        )
    else:
        rows.append(
            (
                "warn",
                "Entry day",
                f"The entry session ({facts.entry_day:%a %d %b}) has already passed for this expiry.",
            )
        )

    if facts.lot_qty == EXPECTED_LOT:
        rows.append(("ok", "Quantity", f"The bot will send {facts.lot_qty} (one lot)."))
    elif facts.lot_qty is None:
        rows.append(("warn", "Quantity", "Could not work out the quantity."))
    else:
        rows.append(
            (
                "fail",
                "Quantity",
                f"The bot would send {facts.lot_qty}, expected {EXPECTED_LOT}.",
            )
        )

    if facts.legs == "two_sided":
        rows.append(("ok", "Option prices", "Both options have a bid and an ask."))
    elif facts.legs == "none" and not facts.market_open:
        rows.append(
            (
                "warn",
                "Option prices",
                "The market is closed, so bid and ask cannot be checked until it opens.",
            )
        )
    elif facts.legs == "none":
        rows.append(
            ("fail", "Option prices", "One of the two options has no bid or ask right now.")
        )
    else:
        rows.append(("warn", "Option prices", "Option prices were not checked."))

    for name in REQUIRED_TASKS:
        text = facts.tasks.get(name)
        if text is None:
            rows.append(("fail", name, f"The scheduled task '{name}' is missing."))
        else:
            rows.append(("ok", name, f"{name}: next run {text}"))

    rows.append(
        (
            "warn",
            "Computer",
            "The PC must be on and signed in before 10:15. A powered-off PC cannot run the bot or the snapshots.",
        )
    )
    return rows


def summary(rows: list[tuple[str, str, str]]) -> tuple[bool, str]:
    """(ready, headline). ready is False if any row is a fail."""
    failures = sum(1 for level, _, _ in rows if level == "fail")
    ready = failures == 0
    other_warns = [row for row in rows if row[0] == "warn" and row[1] != "Computer"]
    if ready and not other_warns:
        headline = "Ready for the dry run."
    elif ready:
        headline = "Ready, with things to confirm."
    else:
        headline = f"Not ready: {failures} problem(s)."
    return ready, headline
