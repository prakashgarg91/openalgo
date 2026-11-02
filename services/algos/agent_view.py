"""Read-only views of the idea register and the forward tests, for the in-app agent and the Algos page.

Nothing here writes a file, runs a screen, records a result, places an order or touches a setting. The
agent toolkit and the page call these and nothing else, so what the agent can see of the research
platform is exactly what this module returns (docs/algos/algo-builder-v2.md).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from services.algos import registry
from utils.logging import get_logger

logger = get_logger(__name__)

CAPITAL = 100_000.0  # the ETF ledgers start with this
C1_TRADES = 24


def register_status(folder: Path, now: datetime) -> dict[str, Any]:
    """The trial count, the bar a forward result must clear, the next free idea month and every idea."""
    count = registry.running_count(folder)
    records = registry._store(folder)
    return {
        "trial_count": count,
        "pass_bar": registry.pass_bar(count),
        "next_free_month": registry.next_free_slot(folder, now),
        "months_used": {
            **registry.SLOTS_USED,
            **{r["slot"]: r["content"]["name"] for r in records},
        },
        "registrations": [
            {
                "id": r["id"],
                "name": r["content"]["name"],
                "registered": r["created_at"][:10],
                "slot": r["slot"],
                "trials": r["trial_numbers"],
                "status": r["status"],
                "intact": registry.intact(r),
            }
            for r in records
        ],
    }


def validate_draft(
    draft: dict[str, Any], folder: Path, now: datetime, known_algo_ids: set[str] | None = None
) -> dict[str, Any]:
    """What would stop this draft from being registered, without registering anything."""
    problems = registry.problems(draft)
    named = (
        (draft.get("params") or {}).get("algo_id")
        if isinstance(draft.get("params"), dict)
        else None
    )
    if named is not None and known_algo_ids is not None and named not in known_algo_ids:
        problems.append(
            "The algo named in the settings (algo_id) is not one of the algos in this app."
        )
    month = f"{now:%Y-%m}"
    if month in registry.SLOTS_USED:
        problems.append(
            f"This month's one new idea is already used by {registry.SLOTS_USED[month]}. "
            f"The next free month is {registry.next_free_slot(folder, now)}."
        )
    elif any(r["slot"] == month for r in registry._store(folder)):
        problems.append(
            f"This month's one new idea is already registered. The next free month is "
            f"{registry.next_free_slot(folder, now)}."
        )
    twin = registry.near_duplicate(draft, folder)
    if twin:
        problems.append(
            f"This restates an idea already registered ({twin}). A reworded idea is the same idea."
        )
    return {
        "ready_to_register": not problems,
        "problems": problems,
        "written": False,
        "note": "Nothing was saved. Only the owner registers an idea, from the Register an idea tab.",
    }


def _c1_row(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        import pandas as pd

        rows = pd.read_csv(path)
        done = int((rows["buy_notional"] > 0).sum()) if "buy_notional" in rows else 0
        net = float(rows["nav"].iloc[-1]) - CAPITAL if len(rows) else 0.0
    except (ValueError, KeyError, OSError):
        logger.exception("Could not read the C1 ledger")
        return None
    return {
        "name": "Month-end NIFTYBEES window (C1)",
        "state": "running",
        "verdict": None,
        "completed": done,
        "trades_to_go": max(0, C1_TRADES - done),
        "net": round(net),
    }


def forward_status() -> list[dict[str, Any]]:
    """Where each forward shadow test stands, from the reports the nightly job writes."""
    rows: list[dict[str, Any]] = []
    s3n = Path(os.getenv("ALGO_FORWARD_S3N_REPORT", "db/forward_s3n/report.json"))
    if s3n.exists():
        try:
            one = json.loads(s3n.read_text(encoding="utf-8"))["ledgers"]["L1"]
            status = one.get("status", {})
            rows.append(
                {
                    "name": "Weekly call spread, 100 points wide (S3n)",
                    "state": status.get("state", "running"),
                    "verdict": status.get("verdict"),
                    "completed": one.get("completed", 0),
                    "trades_to_go": status.get("trades_to_go"),
                    "net": one.get("realistic_net"),
                }
            )
        except (ValueError, KeyError, OSError):
            logger.exception("Could not read the S3n forward report")
    c1 = _c1_row(Path(os.getenv("ALGO_FORWARD_C1_CSV", "db/etf_ledger/c1_calendar_base.csv")))
    if c1:
        rows.append(c1)
    root = Path(os.getenv("ALGO_FORWARD_EOD_DIR", "db/forward_eod"))
    folder = Path(os.getenv("ALGO_REGISTRY_DIR", "db/algo_registry"))
    names = {r["id"]: r["content"]["name"] for r in registry._store(folder)}
    for path in sorted(root.glob("*/report.json")) if root.exists() else []:
        try:
            one = json.loads(path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "name": names.get(path.parent.name, path.parent.name),
                    "state": one["state"],
                    "verdict": one["verdict"],
                    "completed": one["completed"],
                    "trades_to_go": one["trades_to_go"],
                    "net": round(one["stats"]["net"]),
                }
            )
        except (ValueError, KeyError, OSError):
            logger.exception("Could not read a forward report")
    return rows


def tried_before(query: str, docs_root: Path, limit: int = 8) -> list[dict[str, str]]:
    """Lines from the trial register and the results pages that mention every word of the query."""
    words = registry._words(query)
    if not words:
        return []
    files = [docs_root / "TRIAL_REGISTER.md", *sorted(docs_root.glob("*results*.md"))]
    out: list[dict[str, str]] = []
    for path in files:
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if words <= registry._words(line):
                out.append({"file": path.name, "line": str(number), "text": line.strip()[:240]})
                if len(out) >= limit:
                    return out
    return out


FLAG_POINTS = 1.0  # a sandbox fill this many points worse than the ledger's price is worth a look


def reconciliation(path: Path | None = None) -> dict[str, Any]:
    """How the sandbox bot's fills compare with the ledger's candle prices, week by week.

    A positive shortfall means the bot did worse than the ledger assumed. A steady shortfall is the
    measured slippage the cost scenarios assume at 0.15 points a leg. Reads the file the bot's
    ``compare`` command appends to; nothing here places or changes anything.
    """
    path = path or Path(os.getenv("ALGO_BOT_COMPARE_CSV", "db/sandbox_bot/compare.csv"))
    if not path.exists():
        return {"rows": [], "weeks": 0, "mean_entry_shortfall": None, "flag_points": FLAG_POINTS}
    try:
        import pandas as pd

        frame = pd.read_csv(path)
    except (ValueError, OSError):
        logger.exception("Could not read the sandbox comparison file")
        return {"rows": [], "weeks": 0, "mean_entry_shortfall": None, "flag_points": FLAG_POINTS}
    rows = []
    for r in frame.to_dict("records"):
        entry = float(r.get("entry_shortfall", 0) or 0)
        exit_ = r.get("exit_shortfall")
        exit_ = None if exit_ is None or pd.isna(exit_) else float(exit_)
        rows.append(
            {
                "expiry": str(r.get("expiry", "")),
                "ledger_credit": round(float(r.get("ledger_credit", 0) or 0), 2),
                "bot_credit": round(float(r.get("bot_credit", 0) or 0), 2),
                "entry_shortfall": round(entry, 2),
                "exit_shortfall": None if exit_ is None else round(exit_, 2),
                "flagged": abs(entry) >= FLAG_POINTS
                or (exit_ is not None and abs(exit_) >= FLAG_POINTS),
            }
        )
    mean = round(sum(r["entry_shortfall"] for r in rows) / len(rows), 2) if rows else None
    return {
        "rows": rows,
        "weeks": len(rows),
        "mean_entry_shortfall": mean,
        "flag_points": FLAG_POINTS,
    }
