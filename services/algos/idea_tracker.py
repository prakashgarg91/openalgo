"""The Auto Builder idea tracker: what has been tried, how it ended, and what to read before the next idea.

Read only. It decides nothing, runs nothing and places no order. It reshapes the register's own
records (``registry``) into a view with three parts: where every idea stands, the memory of why ideas
failed (the gates they missed), and the size of the hurdle the next idea must clear because of how
many ideas were already tried. Following the search-aware evaluation practice in the research notes
(docs/algos/auto-builder-research-2026-11.md): count every trial, keep a ledger, and never let the
proposer judge its own work.
"""

from __future__ import annotations

from collections import Counter
from statistics import NormalDist
from typing import Any

#: How a register status maps to a stage a trader can read. Anything unknown is shown as is.
STAGE = {
    "registered": "Written down, not yet tested",
    "rejected": "Rejected by its own tests",
    "eligible for a forward test": "Passed the history screen, waiting for a forward test",
    "forward pass": "Forward test passed",
    "forward fail": "Forward test failed",
    "forward inconclusive": "Forward test ended without a clear answer",
}
MAX_LESSONS = 8


def luck_hurdle(count: int, significance: float) -> float:
    """How many standard errors above zero a result must be, once ``count`` ideas were tried.

    This is the one-sided normal quantile of the register's own bar (significance divided by the
    running count). It is a plain restatement of the bar, not a new rule: with more ideas tried, a
    good-looking result is more likely to be luck, so the result has to be stronger.
    """
    if count < 1:
        raise ValueError("count must be at least 1")
    return NormalDist().inv_cdf(1 - significance / count)


def _stage(record: dict[str, Any]) -> str:
    status = str(record.get("status", ""))
    forward = record.get("forward") or {}
    if forward and not forward.get("post_mortem"):
        return f"{STAGE.get(status, status)}; the written post-mortem is still owed"
    return STAGE.get(status, status)


def _idea(record: dict[str, Any], intact: bool) -> dict[str, Any]:
    content = record["content"]
    run = record.get("run") or {}
    return {
        "id": record["id"],
        "name": content["name"],
        "registered": str(record["created_at"])[:10],
        "slot": record["slot"],
        "trial_numbers": record["trial_numbers"],
        "stage": _stage(record) if intact else "Changed after it was frozen; not trusted",
        "failed_gates": list(run.get("failed", [])),
        "why_it_might_work": content["why_it_might_work"],
        "how_it_fails": content["how_it_fails"],
        "intact": intact,
    }


def lessons(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The gates ideas missed most often, plus the failure each one's author feared. This is the
    memory read before proposing the next idea: not a filter, a reading list."""
    missed: Counter[str] = Counter()
    for record in records:
        for gate in (record.get("run") or {}).get("failed", []):
            missed[str(gate)] += 1
    return [{"gate": gate, "ideas_missed": n} for gate, n in missed.most_common(MAX_LESSONS)]


def build(
    records: list[dict[str, Any]],
    intact_ids: set[str],
    trial_count: int,
    significance: float,
    next_free_month: str,
    forward_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the tracker view from values the caller already read (no file or network access)."""
    ideas = [_idea(r, r["id"] in intact_ids) for r in records]
    by_stage = Counter(i["stage"] for i in ideas)
    return {
        "trial_count": trial_count,
        "pass_bar": significance / trial_count,
        "standard_errors_needed": round(luck_hurdle(trial_count, significance), 2),
        "next_free_month": next_free_month,
        "ideas": ideas,
        "stage_counts": dict(by_stage),
        "lessons": lessons(records),
        "forward_tests": forward_rows,
        "live_gate": "locked",
        "rules": [
            "Every idea is written down in full, frozen and counted before it runs.",
            "One new idea a month. A reworded idea is the same idea.",
            "The idea is judged by tests it named in advance, once.",
            "A history screen can only reject an idea or make it eligible for a forward test.",
            "Nothing reaches Live without a forward pass, a written post-mortem and your approval.",
        ],
    }
