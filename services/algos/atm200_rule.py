"""ATM 200-point Nifty call credit spread: the frozen entry and exit rule, as pure functions.

Pure module: no file or network access, no database, no broker, no clock, no logging. Every
input arrives as an argument and every decision leaves as a return value, so the same numbers
always give the same answer.

The rule, as written by the strategy director and not to be changed here:

- Sell a bear call spread at 10:15. The short call sits at the spot rounded to the nearest 50
  (Python round, as in the replay), and the long call sits WIDTH points above it.
- Skip the day when the previous session's India VIX close is 20 or higher. A missing VIX does
  not skip.
- Skip the day when the credit is 5 points or less. There is no other credit floor.
- Exit on bar closes. Target when the spread's value falls to 31 percent of the credit or less,
  stop when it rises to 250 percent of the credit or more, and otherwise leave on the last bar
  at 15:00.

This module places no order. The caller reads the decision and acts on it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

WIDTH = 200  # points between the sold call and the bought call
TARGET = 0.31  # exit when the spread value is at most this share of the credit
STOP = 2.5  # exit when the spread value is at least this multiple of the credit
VIX_SKIP_AT = 20.0  # skip when the previous session's India VIX close is at least this
MIN_CREDIT_POINTS = 5.0  # skip when the credit is at most this many points
MAX_DAYS_TO_EXPIRY = 6  # nearest weekly expiry must be at most this many calendar days away
ENTRY_TIME = "10:15"
LAST_EXIT_TIME = "15:00"
LOT = 65  # Nifty lot size; the caller may pass another lot to pnl_rupees
MAX_LOSS_RUPEES_LEDGER_STOP = 20_000  # ledger stops once cumulative net loss reaches this

REASON_PRICE_MISSING = "A price was missing."
REASON_VIX_HIGH = "The previous India VIX close was 20 or higher."
REASON_CREDIT_SMALL = "The credit was too small to be worth the costs."


@dataclass(frozen=True)
class EntryPlan:
    """What the rule says to do for one entry: the two strikes, the credit, and any skip reason."""

    sold_strike: int | None
    bought_strike: int | None
    credit_points: float | None
    skipped_reason: str | None


def _is_missing(value: float | None) -> bool:
    return value is None or math.isnan(value)


def atm_strike(spot: float) -> int:
    """Spot rounded to the nearest 50 the way the replay that produced the evidence did it (Python's
    round, so an exact half goes to the even multiple: 25025 gives 25000 and 25075 gives 25100)."""
    return int(round(spot / 50) * 50)


def spread_value(sold_price: float, bought_price: float) -> float:
    """Current value of the spread in points: the sold call minus the bought call."""
    return sold_price - bought_price


def plan_entry(
    spot: float | None,
    vix_prev: float | None,
    sold_price: float | None,
    bought_price: float | None,
) -> EntryPlan:
    """Decide the entry at 10:15 from the spot, the previous VIX close and the two call prices.

    Checks run in this order: a missing price or spot, then the VIX gate, then the credit floor.
    A missing VIX passes the VIX gate. The strikes and credit are filled in whenever the inputs
    allow it, even on a skipped day, so the skip can be reported with its numbers.
    """
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


def exit_decision(credit_points: float, current_value: float, is_last_bar: bool) -> str | None:
    """Exit reason for one bar close, or None to hold.

    Target is checked first, then stop. The time exit fires only on the last bar and only when
    neither the target nor the stop has fired.
    """
    if current_value <= TARGET * credit_points:
        return "target"
    if current_value >= STOP * credit_points:
        return "stop"
    if is_last_bar:
        return "time"
    return None


def pnl_rupees(credit_points: float, exit_value_points: float, lot: int = LOT) -> float:
    """Gross rupees for one spread: the points kept (credit minus exit value) times the lot."""
    return (credit_points - exit_value_points) * lot


def ledger_should_stop(cumulative_net_rupees: float) -> bool:
    """True once the cumulative net result has lost MAX_LOSS_RUPEES_LEDGER_STOP or more."""
    return cumulative_net_rupees <= -MAX_LOSS_RUPEES_LEDGER_STOP
