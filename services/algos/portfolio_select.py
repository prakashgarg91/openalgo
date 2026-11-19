"""Walk-forward selector: which algo to trade in each market cell, month by month.

Pure module: no database, broker, network, clock, logging or file access. Every input arrives as
an argument and every result leaves as a return value.

At the start of each month, for each market cell, the selector looks only at trades whose exit
date falls in the trailing window of past months (never the month itself or later). A trade is
judged on the session it closed, so a trade entered in one month and exited in the next counts
from the next month's pick onward. It picks the algo with the best mean net rupees per trade in
that cell. The choice is then frozen for the month.

An algo needs MIN_TRADES_PER_CELL trades in the cell to be eligible. If the best eligible mean is
not strictly positive, or nothing is eligible, the cell gets NO_TRADE.
"""

from __future__ import annotations

from typing import Any

TRAILING_MONTHS = 12
MIN_TRADES_PER_CELL = 40
NO_TRADE = "no_trade"
ALWAYS_NO_TRADE = ("event", "unlabelled")


def month_key(date_str: str) -> str:
    """Return the 'YYYY-MM' month of a 'YYYY-MM-DD' date string."""
    return date_str[:7]


def exit_date_of(trade: dict[str, Any]) -> str:
    """The session a trade closed on, falling back to its entry date when none is recorded."""
    return trade.get("exit_date", trade["date"])


def _month_index(month: str) -> int:
    """Turn 'YYYY-MM' into a running month count, so differences are whole months."""
    year, mon = month.split("-")
    return int(year) * 12 + (int(mon) - 1)


def trailing_window(
    history: list[dict[str, Any]], month: str, months: int = TRAILING_MONTHS
) -> list[dict[str, Any]]:
    """Trades whose exit month is before 'month' and within the last 'months' months.

    The window holds the exit months from (month - months) up to (month - 1), inclusive.
    A trade whose exit date is in 'month' or later is never returned, even if it was entered
    earlier.
    """
    target = _month_index(month)
    return [
        trade
        for trade in history
        if target - months <= _month_index(month_key(exit_date_of(trade))) < target
    ]


def choose(
    history: list[dict[str, Any]],
    month: str,
    cells: list[str],
    algos: list[str],
    trailing_months: int = TRAILING_MONTHS,
    min_trades: int = MIN_TRADES_PER_CELL,
    min_eligible: int = 1,
) -> dict[str, str]:
    """Pick one algo per cell for 'month' from trailing trades only.

    Returns a dict mapping each cell in 'cells' to an algo name from 'algos', or to NO_TRADE.
    'trailing_months' and 'min_trades' default to the registered values above. A cell is traded
    only when at least 'min_eligible' algos are eligible in it; the default of 1 leaves the rule
    as it was (no eligible algo means NO_TRADE).
    """
    window = trailing_window(history, month, trailing_months)
    result: dict[str, str] = {}
    for cell in cells:
        if cell in ALWAYS_NO_TRADE:
            result[cell] = NO_TRADE
            continue
        best_name: str | None = None
        best_mean = 0.0
        eligible = 0
        for algo in sorted(algos):
            nets = [t["net"] for t in window if t["cell"] == cell and t["algo"] == algo]
            if len(nets) < min_trades:
                continue
            eligible += 1
            mean = sum(nets) / len(nets)
            # Strictly greater keeps the alphabetically first algo on an exact tie.
            if best_name is None or mean > best_mean:
                best_name = algo
                best_mean = mean
        if eligible < min_eligible or best_name is None or best_mean <= 0:
            result[cell] = NO_TRADE
        else:
            result[cell] = best_name
    return result


def walk_forward_choices(
    history: list[dict[str, Any]],
    months: list[str],
    cells: list[str],
    algos: list[str],
    trailing_months: int = TRAILING_MONTHS,
    min_trades: int = MIN_TRADES_PER_CELL,
    min_eligible: int = 1,
) -> dict[str, dict[str, str]]:
    """Map each month in 'months' (sorted 'YYYY-MM') to its frozen per-cell choices."""
    return {
        month: choose(history, month, cells, algos, trailing_months, min_trades, min_eligible)
        for month in months
    }
