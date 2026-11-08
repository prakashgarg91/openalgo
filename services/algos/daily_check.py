"""Is today's trading day on track? Pure: the caller gathers the facts.

Three checkpoints run from the Windows Task Scheduler: morning (login, mode, broker session and
yesterday's capture), midday (the 10:15 bid-ask snapshot) and evening (today's capture). This module
performs no I/O, reads no clock and writes no logs. The caller collects a Facts snapshot and receives
plain rows back for display. It places no order.
"""

from dataclasses import dataclass
from datetime import date

WHENS = ("morning", "midday", "evening")
ZEN_STALE_DAYS = 10


@dataclass(frozen=True)
class Facts:
    when: str  # "morning" | "midday" | "evening"
    today: date
    app_up: bool  # OpenAlgo answered
    key_set: bool  # OPENALGO_API_KEY is set (never the value)
    mode: str | None  # "analyze", "live" or None if unknown
    quote_ok: bool  # a quote with a price came back, so the broker session works
    snapshot_labels: set[str]  # bid-ask labels already saved today
    capture_problems: list[str] | None  # problems with today's capture; None when not asked
    yesterday_capture_ok: bool | None  # None when not asked
    zen_file_age_days: float | None  # None when the file is missing


def evaluate(facts: Facts) -> list[tuple[str, str, str]]:
    """Return (level, check, message) rows. level is "ok", "warn" or "fail"."""
    if facts.when == "morning":
        return _morning(facts)
    if facts.when == "midday":
        return _midday(facts)
    return _evening(facts)


def _morning(facts: Facts) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    if not facts.app_up:
        # Mode and broker session cannot be read without OpenAlgo, so they are not reported.
        rows.append(
            ("fail", "OpenAlgo", "OpenAlgo is not running. Start it with Start-OpenAlgo.bat.")
        )
    else:
        rows.append(("ok", "OpenAlgo", "OpenAlgo is running."))
        if not facts.key_set:
            rows.append(("fail", "API key", "The OpenAlgo API key is not set on this PC."))
        else:
            rows.append(("ok", "API key", "The OpenAlgo API key is set."))
            rows.extend(_mode_and_session(facts))

    if facts.yesterday_capture_ok is False:
        rows.append(("warn", "Yesterday's capture", "Yesterday's capture did not finish."))
    elif facts.yesterday_capture_ok:
        rows.append(("ok", "Yesterday's capture", "Yesterday's capture finished."))

    if facts.zen_file_age_days is not None:
        if facts.zen_file_age_days > ZEN_STALE_DAYS:
            rows.append(
                (
                    "warn",
                    "Zen trade file",
                    f"The Zen trade file is {facts.zen_file_age_days:.0f} days old.",
                )
            )
        else:
            rows.append(
                (
                    "ok",
                    "Zen trade file",
                    f"The Zen trade file is {facts.zen_file_age_days:.0f} day(s) old.",
                )
            )
    return rows


def _mode_and_session(facts: Facts) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    if facts.mode == "analyze":
        rows.append(("ok", "Mode", "Analyze mode is on."))
    elif facts.mode == "live":
        rows.append(("fail", "Mode", "OpenAlgo is in Live mode. Switch to Analyze."))
    else:
        rows.append(("warn", "Mode", "Could not tell which mode is on. Check the top bar."))

    if facts.quote_ok:
        rows.append(("ok", "Broker session", "Upstox is connected."))
    else:
        rows.append(
            (
                "fail",
                "Broker session",
                "Upstox is not connected. Sign in to Upstox (the login expires every "
                "morning), then switch to Analyze.",
            )
        )
    return rows


def _midday(facts: Facts) -> list[tuple[str, str, str]]:
    if "1015" not in facts.snapshot_labels:
        return [
            (
                "fail",
                "10:15 snapshot",
                "The 10:15 bid-ask snapshot did not arrive. Check that the PC was on and "
                "OpenAlgo was signed in.",
            )
        ]
    return [("ok", "10:15 snapshot", "The 10:15 bid-ask snapshot is saved.")]


def _evening(facts: Facts) -> list[tuple[str, str, str]]:
    if facts.capture_problems is None:
        return [("warn", "Today's capture", "Today's capture was not checked.")]
    if facts.capture_problems:
        return [
            (
                "fail",
                "Today's capture",
                "Today's capture is not complete: "
                + "; ".join(facts.capture_problems)
                + ". Check log\\capture.log.",
            )
        ]
    return [("ok", "Today's capture", "Today's capture and checks are complete.")]


def headline(rows: list[tuple[str, str, str]]) -> str:
    """One line for the top of the report."""
    flagged = [(level, check) for level, check, _ in rows if level in ("fail", "warn")]
    if not flagged:
        return "All clear."
    n_fail = sum(1 for level, _ in flagged if level == "fail")
    n_warn = len(flagged) - n_fail
    names = ", ".join(check for _, check in flagged[:3])
    return f"{n_fail} problem(s), {n_warn} to confirm: {names}"


def should_alert(rows: list[tuple[str, str, str]]) -> bool:
    """True when any row is a fail. Warnings are shown but do not send an alert."""
    return any(level == "fail" for level, _, _ in rows)
