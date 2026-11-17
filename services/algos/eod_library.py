"""The end-of-day library: five fixed Nifty option structures, valued on NSE end-of-day data.

Rules are fixed in docs/algos/eod-library-registration-DRAFT-2026-11-17.md. This module holds the
library, the leg construction, the expiry-day valuation, the rupee result of one trade after costs,
the cell label, the registered regime group, the effective expiry rule, the best-single-algo
benchmark, the national event list filter and the turning of prepared day rows into trades for the
walk-forward harness.

Pure functions: no database, no broker, no network, no clock, no logging, no file access. Every
input arrives as an argument and every result leaves as a return value.

Only the 'low' cell is tradeable. The 'mid' and 'high' cells are labelled so they can be counted,
but the harness must be called with cells=['low'] only, so they never produce a trade.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Iterable, Mapping
from datetime import date as Date
from typing import Any

import pandas as pd

from services.algos import eod_screen
from services.algos.portfolio_select import exit_date_of, month_key

WIDTH = 200
CONDOR_INNER = 200
CONDOR_OUTER = 400
TRADEABLE_CELLS = ("low",)
EVENT_CELL = "event"
UNLABELLED_CELL = "unlabelled"
LOW_GROUPS = (1, 2)
MID_GROUPS = (3,)
HIGH_GROUPS = (4, 5)

# Registered regime model: ln range of the day on ln previous VIX close and previous range, fitted by
# services/algos/regime_gate.fit on the days up to 2017-07-10 and frozen here. The run script refits
# and refuses unless the refit matches these values within REGIME_TOLERANCE.
REGIME_COEF_VIX_PREV = 0.945791
REGIME_COEF_RANGE_1 = 9.33738
REGIME_INTERCEPT = -7.35624
REGIME_CUTS = (-4.67981, -4.51945, -4.32102, -3.99889)
REGIME_TOLERANCE = 1e-4

# Warm-up months (exit months) that rank the best single algo, and the expiry gap rule.
WARM_UP_FIRST_MONTH = "2021-04"
WARM_UP_LAST_MONTH = "2022-03"
EXPIRY_GAP_DAYS = (1, 2)

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
    the price it settles at. The leg must still have traded on that day: a missing close on the
    expiry day gives None even when the settlement is known. Returns None when the price that applies
    is missing.
    """
    if pd.Timestamp(exit_day) == pd.Timestamp(expiry_day):
        if _missing(settlement) or _missing(close_on_exit):
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


def regime_group(vix_prev: Any, range_1: Any) -> int | None:
    """Registered range group (1 lowest to 5 highest) from the two regime inputs, or None if missing.

    The inputs are the regime_gate.range_frame columns as they are: vix_prev is the natural log of the
    previous session's India VIX close (not the close itself) and range_1 is the previous session's
    range as a fraction of its open. The predicted value is the same linear form as
    regime_gate.groups: vix_prev times its coefficient, plus range_1 times its coefficient, plus the
    intercept. The group is searchsorted(cuts, predicted) + 1, the default side, as in regime_gate.
    """
    if _missing(vix_prev) or _missing(range_1):
        return None
    predicted = (
        REGIME_COEF_VIX_PREV * float(vix_prev)
        + REGIME_COEF_RANGE_1 * float(range_1)
        + REGIME_INTERCEPT
    )
    return bisect.bisect_left(REGIME_CUTS, predicted) + 1


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


def effective_expiries(dates_by_label: Mapping[str, Iterable[str]]) -> dict[str, str]:
    """Effective expiry date for each expiry label, from the dates that label has option rows on.

    dates_by_label maps a label ('YYYY-MM-DD', the expiry the contract carries) to the session dates
    ('YYYY-MM-DD') that have rows for it. A label with rows on its own date keeps that date. A label
    with no rows on its own date uses its last row date only when that date is 1 or 2 calendar days
    before the label (an expiry the exchange moved for a holiday). Any other label is dropped and
    absent from the result. The effective date is the one to use for the expiry window and the
    settlement lookup.
    """
    out: dict[str, str] = {}
    for label, dates in dates_by_label.items():
        label_day = Date.fromisoformat(label)
        days = sorted({Date.fromisoformat(d) for d in dates})
        if label_day in days:
            out[label] = label
        elif days and (label_day - days[-1]).days in EXPIRY_GAP_DAYS:
            out[label] = days[-1].isoformat()
    return out


def best_single_benchmark(
    trades: list[dict[str, Any]], eval_first_month: str, cell: str = "low"
) -> dict[str, Any]:
    """The best single algo, held on every trade of the cell through the evaluation, with no gate.

    The algo is the one with the highest mean net per trade among trades of 'cell' that exit in the
    warm-up months (WARM_UP_FIRST_MONTH to WARM_UP_LAST_MONTH). It is held on every trade of that cell
    that exits from eval_first_month onward. If no algo has a warm-up mean above zero, the benchmark
    is zero and nothing is held.

    The hindsight maximum (the algo with the largest evaluation total, chosen with the evaluation
    results) is returned as well. It is not judged and is not a pass condition.
    """
    warm = [
        t
        for t in trades
        if t["cell"] == cell
        and WARM_UP_FIRST_MONTH <= month_key(exit_date_of(t)) <= WARM_UP_LAST_MONTH
    ]
    best_algo: str | None = None
    best_mean = 0.0
    for algo in sorted(ALGOS):
        nets = [float(t["net"]) for t in warm if t["algo"] == algo]
        if not nets:
            continue
        mean = sum(nets) / len(nets)
        if best_algo is None or mean > best_mean:
            best_algo, best_mean = algo, mean
    evaluation = [
        t for t in trades if t["cell"] == cell and month_key(exit_date_of(t)) >= eval_first_month
    ]
    totals = {
        algo: sum(float(t["net"]) for t in evaluation if t["algo"] == algo)
        for algo in sorted(ALGOS)
    }
    hindsight_algo = max(totals, key=lambda a: totals[a])
    held = best_algo is not None and best_mean > 0
    return {
        "held_algo": best_algo if held else None,
        "warm_up_mean_per_trade": best_mean if best_algo is not None else 0.0,
        "net_total": totals[best_algo] if held else 0.0,
        "hindsight_algo_not_judged": hindsight_algo,
        "hindsight_net_total_not_judged": totals[hindsight_algo],
    }


def usable_event_entries(doc: Mapping[str, Any]) -> list[dict[str, str]]:
    """Event entries ({'date', 'label'}) from the national event file, usable categories only.

    A category is used only when its own 'complete' is True; an incomplete category is left out of
    the rule entirely. The top-level 'complete' is checked by the run script's guard, not here. The
    label is the category name with underscores read as spaces. A malformed date raises ValueError.
    """
    categories = doc.get("categories") or {}
    entries: list[dict[str, str]] = []
    for name in sorted(categories):
        category = categories[name]
        if not isinstance(category, Mapping) or category.get("complete") is not True:
            continue
        for raw in category.get("dates") or []:
            entries.append(
                {"date": Date.fromisoformat(str(raw)).isoformat(), "label": name.replace("_", " ")}
            )
    return sorted(entries, key=lambda e: e["date"])


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
