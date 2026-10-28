"""Which algo, if any, suits this kind of day? Decided from evidence, not from hope.

The table holds, for every algo and every kind of day (calm, trending, volatile, event),
how that algo's past trades on that kind of day did after costs, split in time into an
older evidence period (the first 75 percent of the history) and a newer check period
(the last 25 percent). An algo is eligible for a kind of day only if it made money with
a profit factor of at least 1.2 on enough evidence trades AND still made money on the
newer check trades. Among the eligible, the best average per trade wins. If none is
eligible the answer is to stand aside, and the reasons say why for each algo.

Pure: the table is passed in. ``services/algos/chooser_store.py`` builds and keeps it.
"""

from __future__ import annotations

from typing import Any

from services.algos.context import RELIABLE_CONFIDENCE
from services.algos.lab import summarize

LABELS = ("calm", "trending", "volatile", "event")
EVIDENCE_SHARE = 0.75
MIN_EVIDENCE_TRADES = 30
MIN_CHECK_TRADES = 10
MIN_PROFIT_FACTOR = 1.2


def _cut(trades: list[dict[str, Any]], day: str) -> tuple[list[dict], list[dict]]:
    return [t for t in trades if t["date"] <= day], [t for t in trades if t["date"] > day]


def build_table(trades_by_algo: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Per algo and kind of day: stats on the evidence period and on the check period."""
    dates = sorted(t["date"] for trades in trades_by_algo.values() for t in trades)
    if not dates:
        return {"split": None, "first": None, "last": None, "algos": {}}
    first, last = dates[0], dates[-1]
    split = dates[int(len(dates) * EVIDENCE_SHARE) - 1] if len(dates) > 1 else last
    algos: dict[str, Any] = {}
    for algo_id, trades in trades_by_algo.items():
        per_label = {}
        for label in LABELS:
            mine = [t for t in trades if t.get("regime") == label]
            old, new = _cut(mine, split)
            per_label[label] = {
                "evidence": summarize([t["pnl"] for t in old]),
                "check": summarize([t["pnl"] for t in new]),
            }
        algos[algo_id] = per_label
    return {"split": split, "first": first, "last": last, "algos": algos}


def _pf(stats: dict[str, Any]) -> float:
    """Profit factor, with 'no losing trade at all' (reported as None) counted as unbounded."""
    pf = stats["profit_factor"]
    return float("inf") if pf is None and (stats["total"] or 0) > 0 else (pf or 0.0)


def _why_not(cell: dict[str, Any]) -> list[str]:
    ev, ck = cell["evidence"], cell["check"]
    reasons: list[str] = []
    if ev["trades"] < MIN_EVIDENCE_TRADES:
        reasons.append(
            f"only {ev['trades']} past trades on this kind of day (needs {MIN_EVIDENCE_TRADES})"
        )
    elif (ev["total"] or 0) <= 0:
        reasons.append("lost money on this kind of day in the older years")
    elif _pf(ev) < MIN_PROFIT_FACTOR:
        reasons.append(
            f"profit factor {ev['profit_factor']} in the older years, below {MIN_PROFIT_FACTOR}"
        )
    if not reasons:
        if ck["trades"] < MIN_CHECK_TRADES:
            reasons.append(
                f"only {ck['trades']} trades in the newer years to check against (needs {MIN_CHECK_TRADES})"
            )
        elif (ck["total"] or 0) <= 0:
            reasons.append("good in the older years but lost money in the newer years")
    return reasons


def choose(
    label: str,
    confidence: float,
    table: dict[str, Any] | None,
    names: dict[str, str],
    *,
    candidates: list[str] | None = None,
) -> dict[str, Any]:
    """The pick for this kind of day, with every algo's reasons laid out."""
    if confidence < RELIABLE_CONFIDENCE:
        return {
            "pick": None,
            "headline": "Standing aside: there is too little market data to say what kind of day this is.",
            "candidates": [],
        }
    if not table or not table.get("algos"):
        return {
            "pick": None,
            "headline": "Standing aside: the evidence table has not been built yet.",
            "candidates": [],
        }
    rows = []
    for algo_id, per_label in table["algos"].items():
        if candidates is not None and algo_id not in candidates:
            continue
        cell = per_label.get(label)
        if cell is None:
            continue
        reasons = _why_not(cell)
        rows.append(
            {
                "algo_id": algo_id,
                "name": names.get(algo_id, algo_id),
                "eligible": not reasons,
                "reasons": reasons,
                "evidence": cell["evidence"],
                "check": cell["check"],
            }
        )
    eligible = sorted(
        (r for r in rows if r["eligible"]), key=lambda r: r["evidence"]["avg"], reverse=True
    )
    if not eligible:
        return {
            "pick": None,
            "headline": f"Standing aside: no algo has earned a place on {"an" if label[0] in "aeiou" else "a"} {label} day.",
            "candidates": rows,
        }
    best = eligible[0]
    return {
        "pick": best["algo_id"],
        "headline": (
            f"{best['name']} for a {label} day: Rs {best['evidence']['avg']:,.0f} per trade after costs "
            f"in the older years and still positive in the newer years. Past results, not a promise."
        ),
        "candidates": rows,
    }
