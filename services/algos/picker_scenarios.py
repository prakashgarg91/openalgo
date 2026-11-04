"""What each structure would earn or lose if Nifty ends at a few different levels at expiry. The levels are multiples of one typical move for the days left, from India VIX. Not a forecast.

Pure: no I/O, no clock, no logging. The inputs are priced legs from ``services/algos/picker.py``.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.algos.picker import PricedLeg

MULTIPLES = (-2, -1, 0, 1, 2)


def sigma_points(spot: float, vix: float | None, dte: int) -> float | None:
    """One standard deviation of Nifty, in index points, from now to expiry: spot * vix/100 * sqrt(max(dte, 1) / 252). None when vix is None or not positive."""
    if vix is None or vix <= 0:
        return None
    return spot * (vix / 100.0) * math.sqrt(max(dte, 1) / 252)


def _label(m: int) -> str:
    if m == 0:
        return "No move"
    n = abs(m)
    unit = "move" if n == 1 else "moves"
    direction = "Up" if m > 0 else "Down"
    return f"{direction} {n} typical {unit}"


def _expiry_pnl_pts(legs: list[PricedLeg], level: float) -> float:
    total = 0.0
    for leg in legs:
        intrinsic = (
            max(level - leg.strike, 0.0) if leg.kind == "CE" else max(leg.strike - level, 0.0)
        )
        sign = 1.0 if leg.side == "B" else -1.0
        total += sign * leg.qty * (intrinsic - leg.price)
    return total


def scenario_table(
    legs: list[PricedLeg],
    lot: int,
    spot: float,
    vix: float | None,
    dte: int,
    round_trip_cost: float,
    multiples: tuple[int, ...] = MULTIPLES,
) -> list[dict[str, Any]] | None:
    """One row per multiple, in the order given: {"multiple": m, "label": str, "nifty": level, "pnl": rupees}. None when sigma_points is None."""
    sigma = sigma_points(spot, vix, dte)
    if sigma is None:
        return None
    rows: list[dict[str, Any]] = []
    for m in multiples:
        level = spot + m * sigma
        pnl = lot * _expiry_pnl_pts(legs, level) - round_trip_cost
        rows.append(
            {
                "multiple": m,
                "label": _label(m),
                "nifty": round(level, 1),
                "pnl": float(round(pnl)),
            }
        )
    return rows
