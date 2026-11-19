"""Walk-forward portfolio run: pick an algo per market cell month by month, then judge it.

Pure module: no database, broker, network, clock, logging or file access. Every input arrives
as an argument and every result leaves as a return value.

Two views are returned side by side:

- view_b_walk_forward: each month's per-cell algo is chosen only from trades dated before that
  month (portfolio_select). This is the only view that can count as evidence.
- view_a_hindsight: one algo per cell, chosen with the results of the same evaluation months it
  is judged on. In-sample, not evidence.

Evaluation months are the months that have at least TRAILING_MONTHS earlier months of history,
unless the caller gives a first_month. Both views are scored over those months only.
"""

from __future__ import annotations

from typing import Any

from services.algos import portfolio_report, portfolio_select
from services.algos.portfolio_labels import EVENT_CELL, UNLABELLED_CELL
from services.algos.portfolio_select import (
    MIN_TRADES_PER_CELL,
    TRAILING_MONTHS,
    exit_date_of,
    month_key,
)

HINDSIGHT_LABEL = "in-sample, not evidence"
TRIAL_NOTE = "Each library algo is one trial and the selector is one; hindsight is cells x algos."


def run(
    trades: list[dict[str, Any]],
    cells: list[str],
    algos: list[str],
    first_month: str | None = None,
    trailing_months: int = TRAILING_MONTHS,
    min_trades: int = MIN_TRADES_PER_CELL,
    warmup_months: int | None = None,
    min_eligible: int = 1,
) -> dict[str, Any]:
    """Run both views over the evaluation months of 'trades'.

    'trades' are dicts {'date', 'exit_date', 'algo', 'cell', 'net'}; exit_date is optional and
    falls back to date. Months are exit months: a trade counts in the month its result is known.
    Without first_month the evaluation months are the months after the first warmup_months
    months of history (TRAILING_MONTHS when warmup_months is not given). With first_month they
    are every month from first_month onward ('YYYY-MM'). trailing_months and min_trades go to
    the walk-forward selector; their defaults are the registered values.
    Hindsight picks skip the event and unlabelled cells, as the walk-forward selector does, so
    the two views trade the same days.
    """
    months = sorted({month_key(exit_date_of(t)) for t in trades})
    if first_month is None:
        warmup = TRAILING_MONTHS if warmup_months is None else warmup_months
        eval_months = months[warmup:]
    else:
        eval_months = [m for m in months if m >= first_month]

    eval_set = set(eval_months)
    eval_trades = [t for t in trades if month_key(exit_date_of(t)) in eval_set]

    picks_b = portfolio_select.walk_forward_choices(
        trades, eval_months, cells, algos, trailing_months, min_trades, min_eligible
    )
    days_b = portfolio_report.portfolio_days(eval_trades, picks_b)
    summary_b = portfolio_report.summarise(days_b)
    verdict_b = portfolio_report.verdict(summary_b)

    tradable = [c for c in cells if c not in (EVENT_CELL, UNLABELLED_CELL)]
    hp = portfolio_report.hindsight_picks(eval_trades, tradable, algos)
    days_a = portfolio_report.hindsight_days(eval_trades, hp)
    summary_a = portfolio_report.summarise(days_a)

    return {
        "view_b_walk_forward": {
            "picks": picks_b,
            "summary": summary_b,
            "verdict": verdict_b,
        },
        "view_a_hindsight": {
            "picks": hp,
            "summary": summary_a,
            "label": HINDSIGHT_LABEL,
        },
        "eval_months": eval_months,
        "trial_note": TRIAL_NOTE,
    }
