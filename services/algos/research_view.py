"""What the cross-market research study lets the picker say, and what it does not.

The study (docs/algos/research/linkage.json, written by scripts/algo_backtest/export_linkage_graph.py) found, on
data it had not seen when it chose its links, that overseas markets predict the Nifty's opening gap, and that
nothing it tried predicts the move after the open. This module reads that file and turns today's overseas moves
into a rough expected gap. Pure apart from reading one file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LINKAGE_FILE = Path(__file__).resolve().parents[2] / "docs" / "algos" / "research" / "linkage.json"

#: Our market inputs (``MarketInputs`` field) and the study's node that measures the same thing.
INPUT_TO_NODE = {
    "sp500_pct": "_GSPC",
    "nasdaq_pct": "_IXIC",
    "dxy_pct": "DX-Y.NYB",
}
#: A model is usable only if it beat the trivial baseline on the unseen years by this much (R squared).
MIN_R2_GAIN = 0.05


def load(path: Path | None = None) -> dict[str, Any] | None:
    try:
        return json.loads((path or LINKAGE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def expected_gap(study: dict[str, Any] | None, moves: dict[str, float | None]) -> dict[str, Any]:
    """Average of each verified link's own estimate: its coefficient times today's move in that market.

    Averaging, not adding, because the links overlap (the S&P 500 and the Nasdaq say much the same thing)
    and adding would count one signal several times. A rough estimate, not a forecast."""
    if not study:
        return {"gap_pct": None, "links": []}
    labels = {n["id"]: n.get("label", n["id"]) for n in study.get("nodes", [])}
    verified = {
        link["source"]: link
        for link in study.get("links", [])
        if link.get("target") == "gap" and link.get("status") == "verified"
    }
    parts = []
    for field, node in INPUT_TO_NODE.items():
        move, link = moves.get(field), verified.get(node)
        if move is None or link is None or link.get("beta_ver") is None:
            continue
        parts.append(
            {
                "label": labels.get(node, node),
                "move_pct": float(move),
                "coefficient": float(link["beta_ver"]),
                "implied_gap_pct": float(link["beta_ver"]) * float(move),
            }
        )
    if not parts:
        return {"gap_pct": None, "links": []}
    return {"gap_pct": sum(p["implied_gap_pct"] for p in parts) / len(parts), "links": parts}


def skill(study: dict[str, Any] | None) -> dict[str, Any]:
    """Per outcome: did the joint model beat the baseline on the years it had not seen?"""
    if not study:
        return {}
    out: dict[str, Any] = {}
    names = {
        "gap": "overseas markets predict the opening gap",
        "intraday": "nothing tested predicts the move after the open",
        "range": "the day's range is mostly explained by recent ranges, not by other markets",
    }
    for row in study.get("joint_model", []):
        target = row.get("target")
        if target not in names:
            continue
        gain = float(row["r2_full"]) - float(row["r2_baseline"])
        usable = gain >= MIN_R2_GAIN and float(row["r2_full"]) > 0
        out[target] = {
            "r2": round(float(row["r2_full"]), 3),
            "usable": usable,
            "note": (
                f"Verified on {study.get('meta', {}).get('verification', 'unseen years')}: {names[target]}."
                if usable
                else f"Not usable: {names[target] if target != 'gap' else 'the gap model did not beat its baseline'}."
            ),
        }
    return out
