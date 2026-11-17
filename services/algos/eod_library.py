"""The end-of-day library: five fixed Nifty option structures, valued on NSE end-of-day data.

Rules are fixed in docs/algos/eod-library-registration-DRAFT-2026-11-17.md. This module holds the
library, the leg construction, the expiry-day valuation, the rupee result of one trade after costs,
the cell label and the turning of prepared day rows into trades for the walk-forward harness.

Pure functions: no database, no broker, no network, no clock, no logging, no file access. Every
input arrives as an argument and every result leaves as a return value.

Only the 'low' cell is tradeable. The 'mid' and 'high' cells are labelled so they can be counted,
but the harness must be called with cells=['low'] only, so they never produce a trade.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from services.algos import eod_screen

WIDTH = 200
CONDOR_INNER = 200
CONDOR_OUTER = 400
TRADEABLE_CELLS = ("low",)
EVENT_CELL = "event"
UNLABELLED_CELL = "unlabelled"
LOW_GROUPS = (1, 2)
MID_GROUPS = (3,)
HIGH_GROUPS = (4, 5)

# Each leg: (kind 'CE' or 'PE', strike offset from the ATM strike in points, side 'BUY' or 'SELL').
LIBRARY: dict[str, tuple[tuple[str, int, str], ...]] = {
    "A1": (("CE", 0, "SELL"), ("CE", WIDTH, "BUY")),
    "A2": (("PE", 0, "SELL"), ("PE", -WIDTH, "BUY")),
    "A3": (
        ("CE", CONDOR_INNER, "SELL"),
        ("CE", CONDOR_OUTER, "BUY"),
        ("PE", -CONDOR_INNER, "SELL"),
        ("PE", -CONDOR_OUTER, "BUY"),
    ),
    "A4": (("CE", 0, "BUY"), ("CE", WIDTH, "SELL")),
    "A5": (("PE", 0, "BUY"), ("PE", -WIDTH, "SELL")),
}
ALGOS: tuple[str, ...] = tuple(LIBRARY)


def legs_for(algo: str, atm: int) -> list[tuple[str, int, str]]:
    """The legs of one algo at an at-the-money strike: (kind, absolute strike, side).

    Raises ValueError for an algo that is not in the library.
    """
    if algo not in LIBRARY:
        raise ValueError(f"'{algo}' is not in the library. Known algos: {', '.join(ALGOS)}.")
    return [(kind, int(atm) + offset, side) for kind, offset, side in LIBRARY[algo]]


def settle_value(kind: str, strike: float, settlement: float) -> float:
    """Intrinsic value of one option at expiry, against the index's final settlement price."""
    if kind == "CE":
        return max(float(settlement) - float(strike), 0.0)
    if kind == "PE":
        return max(float(strike) - float(settlement), 0.0)
    raise ValueError(f"kind must be CE or PE, not '{kind}'.")


def clamp_spread_value(value: float, width: float = WIDTH) -> float:
    """A spread's value kept between zero and its width (used for expiry-day exits)."""
    return max(0.0, min(float(value), float(width)))


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def leg_price_exit(
    kind: str,
    strike: float,
    close_on_exit: float | None,
    settlement: float | None,
    expiry_day: Any,
    exit_day: Any,
) -> float | None:
    """The price a leg is closed at on the exit day.

    Normally the option's close on the exit day. When the exit day is the expiry day, the intrinsic
    value against the index settlement price instead, because the expiring contract's close is not
    the price it settles at. Returns None when the price that applies is missing.
    """
    if pd.Timestamp(exit_day) == pd.Timestamp(expiry_day):
        if _missing(settlement):
            return None
        return settle_value(kind, strike, float(settlement))
    if _missing(close_on_exit):
        return None
    return float(close_on_exit)


def trade_net(
    algo: str,
    atm: int,
    entry_prices: list[float | None],
    exit_prices: list[float | None],
    lot: int,
    entry_day: Any,
    exit_day: Any,
    doubled: bool = False,
) -> float:
    """Net rupees of one trade after costs.

    Gross is the sum over legs of side times (exit minus entry) points, times the lot. Costs are the
    sum of eod_screen.leg_cost over every leg. The doubled variant doubles the costs. Prices are in
    the same order as legs_for(algo, atm). A missing price raises ValueError: the caller must drop the
    trade and count it, never fill it in.
    """
    legs = legs_for(algo, atm)
    if len(entry_prices) != len(legs) or len(exit_prices) != len(legs):
        raise ValueError(f"{algo} has {len(legs)} legs; the price lists must match.")
    if any(_missing(p) for p in list(entry_prices) + list(exit_prices)):
        raise ValueError("A leg has no usable price; drop the trade instead.")
    gross_points = 0.0
    costs = 0.0
    for (_kind, _strike, side), entry, exit_ in zip(legs, entry_prices, exit_prices, strict=True):
        sign = 1 if side == "BUY" else -1
        entry, exit_ = float(entry), float(exit_)
        gross_points += sign * (exit_ - entry)
        costs += eod_screen.leg_cost(sign, entry, exit_, entry_day, exit_day, lot)
    multiplier = 2.0 if doubled else 1.0
    return gross_points * lot - multiplier * costs


def cell_for(group: Any, entry_is_event: bool, exit_is_event: bool) -> str:
    """Cell of one trade from its regime group (1 lowest to 5 highest) and its two event flags.

    Either day on an event list gives 'event'. Groups 1 and 2 are 'low', 3 is 'mid', 4 and 5 are
    'high'. Any other group (missing or out of range) is 'unlabelled'.
    """
    if entry_is_event or exit_is_event:
        return EVENT_CELL
    if _missing(group):
        return UNLABELLED_CELL
    if group in LOW_GROUPS:
        return "low"
    if group in MID_GROUPS:
        return "mid"
    if group in HIGH_GROUPS:
        return "high"
    return UNLABELLED_CELL


def build_trades_counted(
    day_rows: list[dict[str, Any]], doubled: bool = False
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Harness trades from prepared day rows, and the counts of what was dropped.

    Each day row is a dict with: entry_date and exit_date ('YYYY-MM-DD'), group, entry_is_event,
    exit_is_event, atm, lot, usable (bool), and legs: {algo: {'entry': [...], 'exit': [...]}} with
    prices in legs_for order. Every algo on every row is one candidate trade. A candidate is dropped
    and counted when its day is not usable (or has no atm or lot), or when any leg price is missing.

    Returns (trades, counts). counts has: candidates, kept, dropped_unusable_day, dropped_unusable_leg.
    """
    trades: list[dict[str, Any]] = []
    counts = {"candidates": 0, "kept": 0, "dropped_unusable_day": 0, "dropped_unusable_leg": 0}
    for row in day_rows:
        cell = cell_for(
            row.get("group"), bool(row.get("entry_is_event")), bool(row.get("exit_is_event"))
        )
        day_ok = (
            bool(row.get("usable")) and row.get("atm") is not None and row.get("lot") is not None
        )
        for algo in ALGOS:
            counts["candidates"] += 1
            if not day_ok:
                counts["dropped_unusable_day"] += 1
                continue
            prices = (row.get("legs") or {}).get(algo)
            if not prices:
                counts["dropped_unusable_leg"] += 1
                continue
            entry_prices, exit_prices = prices.get("entry", []), prices.get("exit", [])
            if len(entry_prices) != len(LIBRARY[algo]) or len(exit_prices) != len(LIBRARY[algo]):
                counts["dropped_unusable_leg"] += 1
                continue
            if any(_missing(p) for p in list(entry_prices) + list(exit_prices)):
                counts["dropped_unusable_leg"] += 1
                continue
            net = trade_net(
                algo,
                int(row["atm"]),
                entry_prices,
                exit_prices,
                int(row["lot"]),
                row["entry_date"],
                row["exit_date"],
                doubled=doubled,
            )
            trades.append(
                {
                    "date": row["entry_date"],
                    "exit_date": row["exit_date"],
                    "algo": algo,
                    "cell": cell,
                    "net": net,
                }
            )
            counts["kept"] += 1
    return trades, counts


def build_trades(day_rows: list[dict[str, Any]], doubled: bool = False) -> list[dict[str, Any]]:
    """The harness trades only. See build_trades_counted for the rules and the counts."""
    return build_trades_counted(day_rows, doubled=doubled)[0]
