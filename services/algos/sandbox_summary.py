"""15:30 end-of-day summary for the ATM 200 Sandbox bot, and the plain-words message for Telegram.

Pure: no database, file, network or clock. The caller reads state.json, trades.csv and the bot log
and passes them in; ``build_summary`` returns a dict and ``render_text`` the message. Charges use the
same schedule as the round-trip ledger (services.algos.sandbox_round_trips.fill_charges), so the
net here matches what the research calls net after charges.

The day is judged on check runs: the log header ``==== DD-MM-YYYY HH:MM`` that ends with ``check``
is one run. Marks run from 09:20 to 15:25 every 5 minutes (74 marks); a run belongs to the mark it
starts in. A gap is two or more missing marks in a row, or a missing mark between 14:55 and 15:05 on
an exit day.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from services.algos.sandbox_round_trips import fill_charges

GRID_START = 9 * 60 + 20  # 09:20
GRID_END = 15 * 60 + 25  # 15:25
STEP = 5
GRID = list(range(GRID_START, GRID_END + 1, STEP))
EXPECTED_CHECKS = len(GRID)  # 74
EXIT_WINDOW = (14 * 60 + 55, 15 * 60 + 5)
#: Statuses that are normal at 15:30. "open" is normal only before its exit session (see _attention).
OK_STATUSES = frozenset({"none", "closed", "skipped", "flat", "not_placed"})

_TIME = re.compile(r"(\d{2}):(\d{2})")


def _minute(line: str, stamp: str) -> int | None:
    """Minutes after midnight of a check run's start time, or None when the header has no time."""
    found = _TIME.search(line.strip()[len(f"==== {stamp}") :])
    if not found:
        return None
    return int(found.group(1)) * 60 + int(found.group(2))


def _is_check_run(line: str, stamp: str) -> bool:
    text = line.strip()
    return text.startswith(f"==== {stamp}") and text.endswith("check")


def _slot(minute: int | None) -> int | None:
    """The grid mark a run belongs to: the 5-minute mark it starts in."""
    if minute is None or not GRID_START <= minute < GRID_END + STEP:
        return None
    return GRID_START + (minute - GRID_START) // STEP * STEP


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _num(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _total(values: list[float | None]) -> float:
    return round(sum(v for v in values if v is not None), 2)


def _net(row: dict[str, Any]) -> tuple[float | None, float | None]:
    """(charges, net after charges) for one trades.csv row, or (None, None) if a fill price is missing."""
    qty = _num(row.get("quantity"))
    entry_day = str(row.get("entry_date") or "")[:10]
    exit_day = str(row.get("exit_time") or row.get("exit_session") or "")[:10]
    legs = [
        ("SELL", _num(row.get("short_fill_price")), entry_day),
        ("BUY", _num(row.get("hedge_fill_price")), entry_day),
        ("BUY", _num(row.get("buyback_fill_price")), exit_day),
        ("SELL", _num(row.get("sell_hedge_fill_price")), exit_day),
    ]
    if qty is None or any(price is None or not day for _, price, day in legs):
        return None, None
    charges = round(sum(fill_charges(action, qty, price, day) for action, price, day in legs), 2)
    gross = _num(row.get("gross_rupees"))
    if gross is None:
        return charges, None
    return charges, round(gross - charges, 2)


def _attention(state: dict[str, Any], now_date: str) -> str | None:
    """The status to name when it needs a person, or None when it is a normal 15:30 state."""
    status = str(state.get("status") or "none")
    if status == "open":
        exit_session = str(state.get("exit_session") or "9999-12-31")
        return "open" if exit_session <= now_date else None
    return None if status in OK_STATUSES else status


def _credit_fill(state: dict[str, Any]) -> float | None:
    if state.get("credit_points") is not None:
        return _num(state.get("credit_points"))
    short, hedge = state.get("short_fill"), state.get("hedge_fill")
    if isinstance(short, dict) and isinstance(hedge, dict):
        s, h = _num(short.get("price")), _num(hedge.get("price"))
        if s is not None and h is not None:
            return round(s - h, 2)
    return None


def recent_runs(bot_log_lines: list[str], count: int = 3) -> list[str]:
    """The last ``count`` run headers (lines starting '==== ') in the bot log."""
    headers = [line.strip() for line in bot_log_lines if line.strip().startswith("==== ")]
    return headers[-count:]


def build_summary(
    state: dict[str, Any],
    trades_rows: list[dict[str, Any]],
    bot_log_lines: list[str],
    expected_checks: int,
    now_date: str,
) -> dict[str, Any]:
    """The day's bot state, check record, gaps, closed trades and cumulative net, with one verdict.

    ``now_date`` is 'YYYY-MM-DD'. The verdict is 'needs attention: <state>', 'check gaps: N' or
    'clean day', in that order of precedence.
    """
    stamp = date.fromisoformat(now_date).strftime("%d-%m-%Y")
    runs = [line for line in bot_log_lines if _is_check_run(line, stamp)]
    hit = {slot for slot in (_slot(_minute(line, stamp)) for line in runs) if slot is not None}

    groups: list[list[int]] = []
    current: list[int] = []
    for mark in GRID:
        if mark in hit:
            if current:
                groups.append(current)
                current = []
        else:
            current.append(mark)
    if current:
        groups.append(current)
    missed = [mark for mark in GRID if mark not in hit]

    closed_rows = [r for r in trades_rows if str(r.get("exit_time") or "")[:10] == now_date]
    exit_day = state.get("exit_session") == now_date or bool(closed_rows)
    gaps: list[dict[str, str]] = []
    for group in groups:
        first, last = _hhmm(group[0]), _hhmm(group[-1])
        if len(group) >= 2:
            gaps.append({"from": first, "to": last, "reason": "two or more checks missed in a row"})
        elif exit_day and EXIT_WINDOW[0] <= group[0] <= EXIT_WINDOW[1]:
            gaps.append(
                {
                    "from": first,
                    "to": last,
                    "reason": "check missed between 14:55 and 15:05 on the exit day",
                }
            )

    closed = []
    for row in closed_rows:
        charges, net = _net(row)
        closed.append(
            {
                "sold": row.get("sold", ""),
                "long": row.get("long", ""),
                "exit_reason": row.get("exit_reason", ""),
                "gross": _num(row.get("gross_rupees")),
                "charges": charges,
                "net": net,
            }
        )
    all_nets = [_net(row)[1] for row in trades_rows]

    attention = _attention(state, now_date)
    if attention:
        verdict = f"needs attention: {attention}"
    elif gaps:
        verdict = f"check gaps: {len(gaps)}"
    else:
        verdict = "clean day"

    return {
        "date": now_date,
        "verdict": verdict,
        "clean": verdict == "clean day",
        "state": {
            "status": str(state.get("status") or "none"),
            "entry_date": state.get("entry_date"),
            "expiry": state.get("expiry"),
            "exit_session": state.get("exit_session"),
            "sold": state.get("sold"),
            "long": state.get("long"),
            "sold_strike": state.get("sold_strike"),
            "bought_strike": state.get("bought_strike"),
            "entry_ltp_credit": _num(state.get("entry_ltp_credit")),
            "credit_fill": _credit_fill(state),
        },
        "checks": {
            "run": len(runs),
            "expected": expected_checks,
            "missed": len(missed),
            "missed_at": [_hhmm(m) for m in missed],
        },
        "gaps": gaps,
        "closed_today": closed,
        "net_today": _total([t["net"] for t in closed]),
        "cumulative_net": _total(all_nets),
        "unpriced_trades": sum(1 for n in all_nets if n is None),
    }


def render_text(summary: dict[str, Any]) -> str:
    """The Telegram message: plain words, starts with 'Sandbox 15:30 summary:'."""
    st = summary["state"]
    day = date.fromisoformat(summary["date"]).strftime("%d %b %Y")
    lines = [f"Sandbox 15:30 summary: {day}. Verdict: {summary['verdict']}."]

    if st["status"] == "none":
        lines.append("No trade in the bot state.")
    else:
        lines.append(
            f"Trade: {st['sold'] or 'no call'} / {st['long'] or 'no hedge'}, "
            f"expiry {st['expiry'] or 'unknown'}, status {st['status']}."
        )
        ltp = "not recorded" if st["entry_ltp_credit"] is None else f"{st['entry_ltp_credit']:.2f}"
        fill = "not recorded" if st["credit_fill"] is None else f"{st['credit_fill']:.2f}"
        lines.append(f"Credit: {ltp} points at the LTP, {fill} points filled.")

    checks = summary["checks"]
    missed_text = f", missed at {', '.join(checks['missed_at'])}" if checks["missed_at"] else ""
    lines.append(
        f"Checks: {checks['run']} logged of {checks['expected']} expected, "
        f"{checks['missed']} missed{missed_text}."
    )
    if summary["gaps"]:
        gap_text = "; ".join(f"{g['from']} to {g['to']} ({g['reason']})" for g in summary["gaps"])
        lines.append(f"Gaps: {gap_text}.")
    else:
        lines.append("Gaps: none.")

    if summary["closed_today"]:
        lines.append(
            f"Closed today: {len(summary['closed_today'])} trade(s), net after charges "
            f"Rs {summary['net_today']:,.0f}."
        )
    else:
        lines.append("Closed today: none.")
    cumulative = f"Cumulative net after charges: Rs {summary['cumulative_net']:,.0f}."
    if summary["unpriced_trades"]:
        cumulative += f" {summary['unpriced_trades']} trade(s) without fill prices not counted."
    lines.append(cumulative)
    return "\n".join(lines)
