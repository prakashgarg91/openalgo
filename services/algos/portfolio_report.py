"""Account result for the chosen algo, built one trading day at a time.

Pure module: no database, broker, network, clock, logging or file access. Every input arrives
as an argument and every result leaves as a return value.

A trade is a dict with a date ('YYYY-MM-DD', the entry), an optional exit_date (the session the
trade closed, which falls back to date when absent), an algo name, a cell and a net result in
rupees. Money is booked on the exit date. A pick map says which algo is chosen for each cell in
each month ('YYYY-MM', the exit month). A day with no
chosen trade is flat, so it is simply absent from the day series. A 'no_trade' pick counts
for nothing.

hindsight_picks and hindsight_days show the best algo for each cell over the whole period.
They are in-sample, not evidence: they choose using the same results they are judged on.
Only a forward shadow run can show whether an algo works.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any, Final

DAILY_CAP_RUPEES: Final = 27000  # the owner's daily loss cap (raised from 20,000 on 17 Nov 2026)
SHADOW_MIN_T: Final = 2.0
SHADOW_MAX_WORST_DAY: Final = 10000
SHADOW_MAX_DRAWDOWN: Final = 20000
NO_TRADE: Final = "no_trade"


def _month_of(date: str) -> str:
    """The month part of a 'YYYY-MM-DD' date string."""
    return date[:7]


def _exit_of(trade: dict[str, Any]) -> str:
    """The session the result is known on: the exit date, or the entry date when none is set."""
    return trade.get("exit_date", trade["date"])


def _day_series(
    trades: Iterable[dict[str, Any]],
    chosen_for: Callable[[dict[str, Any]], str | None],
) -> list[tuple[str, float]]:
    """Sum the net of the chosen trades on each exit date, sorted by date.

    chosen_for returns the algo picked for a trade's cell, or None when nothing is picked.
    Only trades whose algo matches the pick count, and a 'no_trade' pick counts for nothing.
    """
    totals: dict[str, float] = defaultdict(float)
    for trade in trades:
        chosen = chosen_for(trade)
        if chosen is None or chosen == NO_TRADE or trade["algo"] != chosen:
            continue
        totals[_exit_of(trade)] += float(trade["net"])
    return sorted(totals.items())


def portfolio_days(
    trades: Iterable[dict[str, Any]],
    picks: dict[str, dict[str, str]],
) -> list[tuple[str, float]]:
    """Net rupees per trading day, using the algo picked for each cell in the exit month.

    Each trade's net lands on its exit date, the session its result is known, and the pick is
    looked up in the month of that exit date. Days with no chosen trade are left out.
    Two chosen trades on one date are added together.
    """

    def chosen_for(trade: dict[str, Any]) -> str | None:
        return picks.get(_month_of(_exit_of(trade)), {}).get(trade["cell"])

    return _day_series(trades, chosen_for)


def _max_drawdown(nets: list[float]) -> float:
    """Largest fall of the running total from a peak. The peak starts at zero."""
    peak = 0.0
    running = 0.0
    worst = 0.0
    for net in nets:
        running += net
        peak = max(peak, running)
        worst = max(worst, peak - running)
    return worst


def summarise(days: list[tuple[str, float]]) -> dict[str, Any]:
    """Headline numbers for a day series from portfolio_days or hindsight_days.

    t_stat is the mean divided by its standard error, and is 0.0 when there are fewer than
    two days or the standard deviation is zero. positive_halves is True only when the days
    split at the median index both add up to more than zero. An empty series gives zeros.
    """
    nets = [net for _, net in days]
    n = len(nets)
    net_total = sum(nets)
    mean = net_total / n if n else 0.0
    sd = math.sqrt(sum((x - mean) ** 2 for x in nets) / (n - 1)) if n >= 2 else 0.0
    t_stat = mean / (sd / math.sqrt(n)) if n >= 2 and sd > 0 else 0.0

    half = n // 2
    positive_halves = n >= 2 and sum(nets[:half]) > 0 and sum(nets[half:]) > 0

    monthly: dict[str, float] = defaultdict(float)
    for date, net in days:
        monthly[_month_of(date)] += net

    return {
        "n_trades_days": n,
        "net_total": net_total,
        "mean_per_trading_day": mean,
        "sd": sd,
        "t_stat": t_stat,
        "worst_day": min(nets) if nets else 0.0,
        "days_over_cap": sum(1 for x in nets if x <= -DAILY_CAP_RUPEES),
        "max_drawdown": _max_drawdown(nets),
        "positive_halves": positive_halves,
        "months_negative": sum(1 for total in monthly.values() if total < 0),
    }


def hindsight_picks(
    trades: Iterable[dict[str, Any]],
    cells: Iterable[str],
    algos: Iterable[str],
) -> dict[str, str]:
    """For each cell, the algo with the best mean net per trade over the whole period.

    Ties go to the algo name that sorts first. A cell where no algo has a trade gets
    'no_trade'. In-sample, not evidence: the choice uses the results it is judged on.
    """
    trade_list = list(trades)
    algo_names = sorted(algos)
    picks: dict[str, str] = {}
    for cell in cells:
        best_mean: float | None = None
        best_algo = NO_TRADE
        for algo in algo_names:
            nets = [float(t["net"]) for t in trade_list if t["cell"] == cell and t["algo"] == algo]
            if not nets:
                continue
            mean = sum(nets) / len(nets)
            if best_mean is None or mean > best_mean:
                best_mean = mean
                best_algo = algo
        picks[cell] = best_algo
    return picks


def hindsight_days(
    trades: Iterable[dict[str, Any]],
    picks_by_cell: dict[str, str],
) -> list[tuple[str, float]]:
    """Net rupees per day using one fixed algo per cell for the whole period.

    In-sample, not evidence: the choices come from the same results they are judged on.
    """
    return _day_series(trades, lambda trade: picks_by_cell.get(trade["cell"]))


def verdict(summary: dict[str, Any]) -> str:
    """Whether the summary is eligible for a forward shadow run, or the first reason it is not.

    The checks run in this order: t statistic, both halves positive, worst day, drawdown,
    daily cap. Passing all of them gives 'eligible for forward shadow'.
    """
    if summary["t_stat"] < SHADOW_MIN_T:
        return f"The t statistic is below {SHADOW_MIN_T:.1f}."
    if not summary["positive_halves"]:
        return "The two halves of the period are not both positive."
    if summary["worst_day"] <= -SHADOW_MAX_WORST_DAY:
        return f"A single day lost {SHADOW_MAX_WORST_DAY:,} rupees or more."
    if summary["max_drawdown"] >= SHADOW_MAX_DRAWDOWN:
        return f"The largest drawdown is {SHADOW_MAX_DRAWDOWN:,} rupees or more."
    if summary["days_over_cap"] > 0:
        return f"At least one day lost {DAILY_CAP_RUPEES:,} rupees or more, the daily cap."
    return "eligible for forward shadow"
