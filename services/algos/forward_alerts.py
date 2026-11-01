"""Telegram alerts for the forward shadow test, so a lost week is noticed the same evening.

The message builders are pure functions; only ``notify`` touches Telegram, and it imports the alert
service lazily so a missing bot never stops the nightly job. A message is also printed, so it
reaches ``log\\capture.log`` whether or not Telegram is switched on.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def capture_message(code: int, day: str) -> str | None:
    """What a trader should read when the nightly capture did not finish cleanly."""
    if code == 0:
        return None
    if code == 3:
        return (
            f"Nightly capture for {day}: no Nifty candles came back on a weekday. If the market was "
            "open, Upstox did not accept the analytics token or did not answer. Check the token and "
            "run the capture again tonight, or this week may not count in the forward test."
        )
    if code == 2:
        return (
            f"Nightly capture for {day}: some option candles could not be saved. Run the capture "
            "again; a week with a missing entry or expiry day is not counted in the forward test."
        )
    return (
        f"Nightly capture for {day} stopped before saving (exit code {code}). Check log\\capture.log, "
        "then run the capture again."
    )


def missing_day_message(
    stored_days: list, today: date, holidays: set[date] | None = None
) -> str | None:
    """Warn when a weekday between the last stored session and today has no stored candles.

    ``holidays`` is optional; without it a market holiday also triggers the message, which then
    says so. Today itself is not checked: the capture runs after the close.
    """
    if not stored_days:
        return "No option candles are stored yet. Run the nightly capture after a trading day."
    last = max(d.date() if hasattr(d, "date") else d for d in stored_days)
    holidays = holidays or set()
    gaps, cursor = [], last + timedelta(days=1)
    while cursor < today:
        if cursor.weekday() < 5 and cursor not in holidays:
            gaps.append(cursor)
        cursor += timedelta(days=1)
    if not gaps:
        return None
    names = ", ".join(f"{g:%a %d %b}" for g in gaps[:5])
    return (
        f"No option candles are stored for {names}. If the market was open, run the capture for "
        "that day; a missed entry or expiry day removes that week from the forward test. "
        "If it was a market holiday, ignore this."
    )


def events(report: dict[str, Any], seen: set[str]) -> tuple[list[str], set[str]]:
    """Messages for what is new in the L1 ledger since the last run, and the updated seen set."""
    ledger = report["ledgers"]["L1"]
    out, now = [], set(seen)

    def once(key: str, text: str) -> None:
        if key not in now:
            now.add(key)
            out.append(text)

    for week in ledger["not_counted"]:
        once(
            f"skip:{week['expiry']}:{week['reason']}",
            f"Forward test: the week of the {week['expiry']} expiry was NOT counted ({week['reason']}).",
        )
    for t in ledger["open"]:
        once(
            f"open:{t['expiry'][:10]}",
            f"Forward test: entered the {t['expiry'][:10]} expiry week at {t['entry']}, credit "
            f"{t['credit']:.2f} points. Sandbox shadow; no order was placed.",
        )
    for t in ledger["trades"]:
        once(
            f"done:{t['expiry'][:10]}",
            f"Forward test: the {t['expiry'][:10]} week closed, net Rs {t['net']:,.0f} after "
            f"realistic costs. {ledger['completed']} of 26 trades done.",
        )
    status = ledger.get("status", {})
    if status.get("state") in ("stopped", "finished"):
        once(
            f"state:{status['state']}:{status.get('verdict')}",
            f"Forward test {status['state']}: verdict {status.get('verdict')}. "
            f"Realistic net Rs {ledger['realistic_net']:,}.",
        )
    return out, now


def notify(message: str) -> bool:
    """Print the message and send it to every Telegram user with notifications on."""
    print(f"ALERT: {message}")
    try:
        from database.telegram_db import get_all_telegram_users
        from services.telegram_alert_service import telegram_alert_service

        if not telegram_alert_service.is_bot_active():
            print("(Telegram bot is off, so this alert was only written to the log.)")
            return False
        sent = False
        for user in get_all_telegram_users({}):
            if user.get("notifications_enabled"):
                sent |= bool(telegram_alert_service.send_alert_sync(user["telegram_id"], message))
        return sent
    except Exception:
        from utils.logging import get_logger

        get_logger(__name__).exception("Could not send the forward test alert")
        return False
