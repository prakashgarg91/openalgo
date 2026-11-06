"""Shadow follow ledger for Stratzy Zen's published credit spread advices.

Pure module: no file or network access, no clock, no logging. Every input arrives as an argument
and every result leaves as a return value. It works out what one lot of each published advice
would have made after charges, using the cost schedule in services/algos/eod_screen.py.

Nothing here places an order. The ledger reads the advices and reports the numbers.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from services.algos.eod_screen import leg_cost
from services.algos.zen_trades import ZenTrade

UNSEEN_AFTER = date(2026, 9, 23)
VARIANTS = ("all", "calls")
INCONCLUSIVE_BELOW = 20  # unseen call trades needed before any verdict is given
TRADES_FOR_VERDICT = 30  # reported as trades_needed only
DRAWDOWN_LIMIT = 20_000.0
WORST_DAY_LIMIT = -10_000.0
STALE_DAYS = 10
NOT_CLAIMED = (
    "The register's statistical bar is not claimed here. "
    "This ledger reports the numbers; it does not test them."
)


def cost_one_lot(trade: ZenTrade, multiplier: float = 1.0) -> float | None:
    """Charges for one lot over the round trip of both legs, times multiplier.

    None when any of the four leg prices or the exit time is missing.
    """
    prices = (trade.sold_entry, trade.long_entry, trade.sold_exit, trade.long_exit)
    if trade.exit_time is None or any(price is None for price in prices):
        return None
    entry_day = pd.Timestamp(trade.entry_time.date())
    exit_day = pd.Timestamp(trade.exit_time.date())
    lot = trade.lot_size
    sold = leg_cost(-1, trade.sold_entry, trade.sold_exit, entry_day, exit_day, lot)
    bought = leg_cost(1, trade.long_entry, trade.long_exit, entry_day, exit_day, lot)
    return (sold + bought) * multiplier


def net_one_lot(trade: ZenTrade, multiplier: float = 1.0) -> float | None:
    """Rupees kept for one lot after charges. None for an open or unpriced trade."""
    charges = cost_one_lot(trade, multiplier)
    if charges is None:
        return None
    points = (trade.sold_entry - trade.long_entry) - (trade.sold_exit - trade.long_exit)
    return points * trade.lot_size - charges


def _when(row: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(row["entry_time"])


def rows_for(trades: list[ZenTrade], variant: str) -> list[dict[str, Any]]:
    """One row per closed trade in the variant, oldest entry first. Open trades are left out."""
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}, not {variant!r}")
    rows: list[dict[str, Any]] = []
    for trade in sorted(trades, key=lambda t: t.entry_time):
        if variant == "calls" and trade.kind != "CE":
            continue
        net = net_one_lot(trade)
        if net is None:
            continue
        net_2x = net_one_lot(trade, 2.0)
        rows.append(
            {
                "advice_id": trade.advice_id,
                "entry_time": trade.entry_time.isoformat(),
                "kind": trade.kind,
                "sold_strike": trade.sold_strike,
                "long_strike": trade.long_strike,
                "net": round(net, 2),
                "net_2x": round(net_2x, 2),
                "unseen": trade.entry_time.date() > UNSEEN_AFTER,
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals and risk figures for rows from rows_for. Undefined ratios are None, never zero."""
    ordered = sorted(rows, key=_when)
    nets = [float(r["net"]) for r in ordered]
    count = len(nets)
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    total = sum(nets)

    day_totals: dict[date, float] = {}
    for r in ordered:
        day = _when(r).date()
        day_totals[day] = day_totals.get(day, 0.0) + float(r["net"])

    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for n in nets:
        cumulative += n
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)

    return {
        "trades": count,
        "wins": len(wins),
        "win_rate": round(len(wins) / count, 4) if count else None,
        "net": round(total, 2),
        "net_2x": round(sum(float(r["net_2x"]) for r in ordered), 2),
        "mean": round(total / count, 2) if count else None,
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
        "average_win": round(gross_win / len(wins), 2) if wins else None,
        "average_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "worst_trade": round(min(nets), 2) if nets else 0.0,
        "worst_day": round(min(day_totals.values()), 2) if day_totals else 0.0,
        "drawdown": round(drawdown, 2),
    }


def gates(unseen_calls: dict[str, Any], unseen_all: dict[str, Any]) -> dict[str, Any]:
    """Survival checks for the calls variant on the unseen window only.

    The inputs are summaries from summarize. The outcome is inconclusive below
    INCONCLUSIVE_BELOW unseen call trades, supported when all five checks pass, and
    unsupported otherwise.
    """
    trades = int(unseen_calls.get("trades") or 0)
    net = float(unseen_calls.get("net") or 0.0)
    net_2x = float(unseen_calls.get("net_2x") or 0.0)
    drawdown = float(unseen_calls.get("drawdown") or 0.0)
    worst_day = float(unseen_calls.get("worst_day") or 0.0)
    all_drawdown = float(unseen_all.get("drawdown") or 0.0)

    checks = {
        "g1_net_positive": net > 0,
        "g2_net_2x_positive": net_2x > 0,
        "g3_drawdown_under_20000": drawdown < DRAWDOWN_LIMIT,
        "g4_worst_day_above_minus_10000": worst_day > WORST_DAY_LIMIT,
        "g5_drawdown_below_zen_all": drawdown < all_drawdown,
    }
    if trades < INCONCLUSIVE_BELOW:
        outcome = "inconclusive"
    elif all(checks.values()):
        outcome = "supported"
    else:
        outcome = "unsupported"
    return {
        **checks,
        "unseen_calls_trades": trades,
        "outcome": outcome,
        "trades_needed": max(0, TRADES_FOR_VERDICT - trades),
        "note": NOT_CLAIMED,
    }


def report(trades: list[ZenTrade], file_age_days: float | None) -> dict[str, Any]:
    """The full ledger view: seen and unseen summaries, open count, gates and warnings."""
    all_rows = rows_for(trades, "all")
    call_rows = rows_for(trades, "calls")
    seen_all = [r for r in all_rows if not r["unseen"]]
    seen_calls = [r for r in call_rows if not r["unseen"]]
    unseen_all = summarize([r for r in all_rows if r["unseen"]])
    unseen_calls = summarize([r for r in call_rows if r["unseen"]])

    warnings: list[str] = []
    if file_age_days is not None and file_age_days > STALE_DAYS:
        warnings.append(
            f"The Zen trade file is {file_age_days:.0f} days old. Ask for a fresh download."
        )
    if unseen_all["trades"] == 0:
        warnings.append("No Zen trades after 23 Sep 2026 are in the file yet.")

    latest = max((t.entry_time for t in trades), default=None)
    return {
        "seen": {"all": summarize(seen_all), "calls": summarize(seen_calls)},
        "unseen": {"all": unseen_all, "calls": unseen_calls},
        "open_trades": sum(1 for t in trades if t.exit_time is None),
        "unpriced_trades": sum(
            1 for t in trades if t.exit_time is not None and net_one_lot(t) is None
        ),
        "trades_in_file": len(trades),
        "gates": gates(unseen_calls, unseen_all),
        "latest_entry": latest.isoformat() if latest else None,
        "stale_warning": " ".join(warnings) or None,
    }
