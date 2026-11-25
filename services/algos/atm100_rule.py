"""ATM 100-point Nifty call credit spread: pure entry and exit rules."""

from __future__ import annotations

import math
from dataclasses import dataclass

from services.algos.atm200_rule import atm_strike, exit_decision, pnl_rupees, spread_value

WIDTH = 100
TARGET = 0.31
STOP = 2.5
VIX_SKIP_AT = 20.0
MIN_CREDIT_POINTS = 3.0
MAX_DAYS_TO_EXPIRY = 6
ENTRY_TIME = "10:15"
LAST_EXIT_TIME = "15:00"
LOT = 65
MAX_LOSS_RUPEES_LEDGER_STOP = 20_000

REASON_PRICE_MISSING = "A price was missing."
REASON_VIX_HIGH = "The previous India VIX close was 20 or higher."
REASON_CREDIT_SMALL = "The credit was too small to be worth the costs."


@dataclass(frozen=True)
class EntryPlan:
    """The strikes, credit and optional reason to skip one entry."""

    sold_strike: int | None
    bought_strike: int | None
    credit_points: float | None
    skipped_reason: str | None


def _is_missing(value: float | None) -> bool:
    return value is None or math.isnan(value)


def plan_entry(
    spot: float | None,
    vix_prev: float | None,
    sold_price: float | None,
    bought_price: float | None,
) -> EntryPlan:
    """Apply missing price, VIX, then credit checks in that order."""
    if _is_missing(spot) or _is_missing(sold_price) or _is_missing(bought_price):
        return EntryPlan(None, None, None, REASON_PRICE_MISSING)

    sold_strike = atm_strike(spot)
    bought_strike = sold_strike + WIDTH
    credit = spread_value(sold_price, bought_price)

    if not _is_missing(vix_prev) and vix_prev >= VIX_SKIP_AT:
        return EntryPlan(sold_strike, bought_strike, credit, REASON_VIX_HIGH)
    if credit <= MIN_CREDIT_POINTS:
        return EntryPlan(sold_strike, bought_strike, credit, REASON_CREDIT_SMALL)
    return EntryPlan(sold_strike, bought_strike, credit, None)


def ledger_should_stop(cumulative_net_rupees: float) -> bool:
    """True once the cumulative net result has lost the configured ledger stop."""
    return cumulative_net_rupees <= -MAX_LOSS_RUPEES_LEDGER_STOP
