"""Vendor decider: pick one vendor algo per market condition each month, walk-forward, and judge it.

Pure module: no database, broker, network, clock, logging or file access. Every input arrives as
an argument and every result leaves as a return value.

The pool is a fixed list of vendor algos. Each algo reported one number per day it traded: its
result as a percent of its own maximum allocation (percent points per day). Only days on or after
the algo's live_since date are used, because earlier days are the vendor's backtest. Each day has
one market cell: 'nervous' or 'calm', by where the previous session's India VIX close sits
against the median of the VIX_MEDIAN_SESSIONS closes before it. Every month the selector picks,
for each cell, the one algo with the best mean result in the trailing months, and holds it for
that month.

Two views are returned side by side, as in portfolio_wf:

- view_b_walk_forward: the picks use only earlier months. This is the only view that can count
  as evidence.
- view_a_hindsight: one algo per cell chosen on the evaluation days it is judged on. In-sample,
  not evidence.

Two benchmarks are also reported: following every algo equally, and holding the single algo that
was best during the warm-up months for the whole evaluation.

The daily results are percent points, not rupees. The summary fields that portfolio_report names
in rupees (days_over_cap, and the rupee cap behind it) are therefore not meaningful here, and the
verdict in this module does not use them. The verdict is written here, from percent-based lines.
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable
from typing import Any, Final

from services.algos import portfolio_report, portfolio_wf
from services.algos.portfolio_select import NO_TRADE, exit_date_of, month_key

# Frozen constants. The registration document fixes these values before the single real run.
TRAILING_MONTHS: Final[int] = 6
MIN_DAYS_PER_CELL: Final[int] = 15
MIN_ELIGIBLE_ALGOS: Final[int] = 6
FIRST_EVAL_MONTH: Final[str] = "2025-08"
LAST_EVAL_MONTH: Final[str] = "2026-10"
CELLS: Final[tuple[str, ...]] = ("calm", "nervous")
USE_CELLS: Final[bool] = True
VIX_MEDIAN_SESSIONS: Final[int] = 60

# Cell used for every day when USE_CELLS is False, and the label of a day with no cell.
ALL_CELL: Final[str] = "all"
UNLABELLED: Final[str] = "unlabelled"

# Verdict lines.
PASS_MIN_T: Final[float] = 2.0
MIN_EVAL_DAYS: Final[int] = 80
HINDSIGHT_LABEL: Final[str] = "in-sample, not evidence"
INCONCLUSIVE_TOO_FEW: Final[str] = "inconclusive: too few days"
PASS_VERDICT: Final[str] = "pass"


def _missing(value: Any) -> bool:
    """None and NaN both mean 'not known'."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def live_days(daily: dict[str, float], live_since: str) -> dict[str, float]:
    """Only the days on or after live_since. Earlier days are vendor backtest and are never used.

    Dates are 'YYYY-MM-DD' strings, so string order is date order.
    """
    return {day: pct for day, pct in daily.items() if day >= live_since}


def relative_vix_cell(vix_prev_close: Any, earlier_closes: Iterable[Any]) -> str:
    """'nervous' when the previous close is strictly above the median of the earlier closes, else 'calm'.

    'earlier_closes' are the closes before the previous session, oldest first. Only the most
    recent VIX_MEDIAN_SESSIONS of them are used. UNLABELLED when there are fewer than that many,
    or when the previous close or any closes in the window are missing or NaN.
    """
    window = list(earlier_closes)[-VIX_MEDIAN_SESSIONS:]
    if _missing(vix_prev_close) or len(window) < VIX_MEDIAN_SESSIONS:
        return UNLABELLED
    if any(_missing(value) for value in window):
        return UNLABELLED
    median = statistics.median(float(value) for value in window)
    return "nervous" if float(vix_prev_close) > median else "calm"


def cells_by_day(
    vix_closes: list[tuple[str, Any]],
    session_dates: Iterable[str],
) -> dict[str, str]:
    """Cell for each session date, from India VIX closes dated strictly before that date only.

    'vix_closes' are (ISO date, close) pairs. For a session, the previous close is the latest
    close dated before it, and the earlier closes are the closes before that one. A session with
    no earlier close is UNLABELLED. Changing a close on or after a session never changes its cell.
    """
    ordered = sorted(vix_closes, key=lambda pair: pair[0])
    dates = [day for day, _ in ordered]
    values = [close for _, close in ordered]
    cells: dict[str, str] = {}
    for day in session_dates:
        count_before = bisect_left(dates, day)
        if count_before == 0:
            cells[day] = UNLABELLED
            continue
        previous = count_before - 1
        window_start = max(0, previous - VIX_MEDIAN_SESSIONS)
        cells[day] = relative_vix_cell(values[previous], values[window_start:previous])
    return cells


def build_trades(
    pool: list[dict[str, Any]],
    cell_of_day: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Harness trades, one per algo per live day, and a count of the results dropped.

    'pool' items are {'algo_id', 'name', 'category', 'live_since', 'daily'}, where daily maps an
    'YYYY-MM-DD' date to the percent result. Each trade is {'date', 'exit_date', 'algo', 'cell',
    'net'} with date equal to exit_date (the day), and net the percent result.

    The cell is taken from cell_of_day as it is. A day with no cell, or the cell UNLABELLED, is
    dropped and counted as {'unlabelled': n}, one count per dropped algo-day result. With
    USE_CELLS False every day is the single cell 'all' and nothing is dropped.
    """
    trades: list[dict[str, Any]] = []
    dropped: dict[str, int] = {UNLABELLED: 0}
    for item in pool:
        for day, pct in sorted(live_days(item["daily"], item["live_since"]).items()):
            if not USE_CELLS:
                cell = ALL_CELL
            else:
                cell = cell_of_day.get(day, UNLABELLED)
                if cell == UNLABELLED:
                    dropped[UNLABELLED] += 1
                    continue
            trades.append(
                {
                    "date": day,
                    "exit_date": day,
                    "algo": item["algo_id"],
                    "cell": cell,
                    "net": float(pct),
                }
            )
    trades.sort(key=lambda t: (t["date"], t["algo"]))
    return trades, dropped


def equal_weight_benchmark(
    trades: Iterable[dict[str, Any]], eval_months: Iterable[str]
) -> list[tuple[str, float]]:
    """Follow everything: each evaluation day's mean result across the algos that reported that day.

    No cell gating. Returns (date, mean) pairs sorted by date, for days in eval_months only.
    """
    eval_set = set(eval_months)
    by_day: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        day = exit_date_of(trade)
        if month_key(day) in eval_set:
            by_day[day].append(float(trade["net"]))
    return [(day, sum(nets) / len(nets)) for day, nets in sorted(by_day.items())]


def warmup_best_benchmark(
    trades: Iterable[dict[str, Any]],
    first_eval_month: str,
    eval_months: Iterable[str],
) -> tuple[str | None, list[tuple[str, float]]]:
    """The single algo with the best mean daily result before the evaluation, held on the evaluation.

    The warm-up is every trade month before 'first_eval_month'. The algo is held on every
    evaluation day it reports. When no algo has a positive warm-up mean, the algo is None and the
    series is zero on every evaluation day. Returns (algo or None, [(date, pct), ...]).
    """
    trade_list = list(trades)
    warm = {
        month_key(exit_date_of(t))
        for t in trade_list
        if month_key(exit_date_of(t)) < first_eval_month
    }
    eval_set = set(eval_months)

    sums: dict[str, list[float]] = defaultdict(list)
    for trade in trade_list:
        if month_key(exit_date_of(trade)) in warm:
            sums[trade["algo"]].append(float(trade["net"]))

    best: str | None = None
    best_mean = 0.0
    for algo in sorted(sums):
        mean = sum(sums[algo]) / len(sums[algo])
        # Strictly greater keeps the alphabetically first algo on an exact tie.
        if best is None or mean > best_mean:
            best, best_mean = algo, mean
    if best is not None and best_mean <= 0:
        best = None

    eval_trades = [t for t in trade_list if month_key(exit_date_of(t)) in eval_set]
    if best is None:
        days = sorted({exit_date_of(t) for t in eval_trades})
        return None, [(day, 0.0) for day in days]
    held = [(exit_date_of(t), float(t["net"])) for t in eval_trades if t["algo"] == best]
    return best, sorted(held)


def verdict_lines(
    eval_days: int,
    t_stat: float,
    positive_halves: bool,
    walk_forward_total: float,
    equal_weight_total: float,
    warmup_best_total: float,
) -> str:
    """'pass', 'inconclusive: too few days', or 'fail: ...' naming the first line that failed.

    The lines are checked in this order: enough days, t statistic, both halves positive, beats
    following every algo equally, beats the warm-up best algo.
    """
    if eval_days < MIN_EVAL_DAYS:
        return INCONCLUSIVE_TOO_FEW
    if t_stat < PASS_MIN_T:
        return f"fail: the t statistic is {t_stat:.2f}, below {PASS_MIN_T:.1f}."
    if not positive_halves:
        return "fail: the two halves of the period are not both positive."
    if walk_forward_total <= equal_weight_total:
        return "fail: the walk-forward total does not beat following every algo equally."
    if walk_forward_total <= warmup_best_total:
        return "fail: the walk-forward total does not beat the best algo of the warm-up months."
    return PASS_VERDICT


def evaluate(
    pool: list[dict[str, Any]],
    cell_of_day: dict[str, str],
) -> dict[str, Any]:
    """Run the decider over the pool and return both views, the benchmarks and the verdict.

    Evaluation months run from FIRST_EVAL_MONTH to LAST_EVAL_MONTH inclusive. Months before the
    first are look-back history and warm-up only; months after the last are not read at all.
    Picks use portfolio_wf.run with TRAILING_MONTHS, MIN_DAYS_PER_CELL and MIN_ELIGIBLE_ALGOS.
    The walk-forward daily series holds the picked algo's result on each day it reports, in
    percent points.
    """
    trades_all, dropped = build_trades(pool, cell_of_day)
    trades = [t for t in trades_all if month_key(exit_date_of(t)) <= LAST_EVAL_MONTH]
    cells = list(CELLS) if USE_CELLS else [ALL_CELL]
    algos = sorted({item["algo_id"] for item in pool})
    category_of = {item["algo_id"]: item["category"] for item in pool}

    run = portfolio_wf.run(
        trades,
        cells=cells,
        algos=algos,
        first_month=FIRST_EVAL_MONTH,
        trailing_months=TRAILING_MONTHS,
        min_trades=MIN_DAYS_PER_CELL,
        min_eligible=MIN_ELIGIBLE_ALGOS,
    )
    eval_months = run["eval_months"]
    eval_set = set(eval_months)
    eval_trades = [t for t in trades if month_key(exit_date_of(t)) in eval_set]

    picks_b = run["view_b_walk_forward"]["picks"]
    days_b = portfolio_report.portfolio_days(eval_trades, picks_b)
    summary_b = portfolio_report.summarise(days_b)

    picks_a = run["view_a_hindsight"]["picks"]
    days_a = portfolio_report.hindsight_days(eval_trades, picks_a)
    summary_a = portfolio_report.summarise(days_a)

    equal_days = equal_weight_benchmark(trades, eval_months)
    equal_summary = portfolio_report.summarise(equal_days)
    warm_algo, warm_days = warmup_best_benchmark(trades, FIRST_EVAL_MONTH, eval_months)
    warm_summary = portfolio_report.summarise(warm_days)

    category_picks: dict[str, int] = defaultdict(int)
    cell_months_no_trade = 0
    for month in eval_months:
        for cell in cells:
            pick = picks_b[month][cell]
            if pick == NO_TRADE:
                cell_months_no_trade += 1
            else:
                category_picks[category_of[pick]] += 1

    verdict = verdict_lines(
        eval_days=len(days_b),
        t_stat=summary_b["t_stat"],
        positive_halves=summary_b["positive_halves"],
        walk_forward_total=summary_b["net_total"],
        equal_weight_total=equal_summary["net_total"],
        warmup_best_total=warm_summary["net_total"],
    )

    return {
        "view_b_walk_forward": {"picks": picks_b, "summary": summary_b, "days": days_b},
        "view_a_hindsight": {
            "picks": picks_a,
            "summary": summary_a,
            "days": days_a,
            "label": HINDSIGHT_LABEL,
        },
        "benchmarks": {
            "equal_weight": {"summary": equal_summary, "days": equal_days},
            "warmup_best": {"algo": warm_algo, "summary": warm_summary, "days": warm_days},
        },
        "category_picks": dict(sorted(category_picks.items())),
        "cell_months_no_trade": cell_months_no_trade,
        "eval_months": eval_months,
        "eval_days": len(days_b),
        "dropped_results": dropped,
        "verdict": verdict,
    }
