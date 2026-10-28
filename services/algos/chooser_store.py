"""Building, keeping and using the chooser's evidence table, and the Smart Pick algo on top of it.

The table is rebuilt in a background process (it replays every overnight algo over ten
years) and kept as one small JSON file. The daily runner only ever reads it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.algos import chooser
from services.algos.context import RegimeResult
from services.algos.templates import ALGOS, Plan, build
from utils.logging import get_logger

logger = get_logger(__name__)

TABLE_PATH = Path(__file__).resolve().parents[2] / "db" / "algo_chooser" / "table.json"
SMART_PICK = "smart_pick"
#: Smart Pick enters at the close and exits next morning, like the algos it chooses among,
#: so only overnight algos may be picked.
STALE_AFTER_DAYS = 45


def candidate_ids() -> list[str]:
    return [a for a, spec in ALGOS.items() if spec.overnight and a != SMART_PICK]


def save_table(table: dict[str, Any], path: Path = TABLE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**table, "built_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(path)


def load_table(path: Path = TABLE_PATH) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def names() -> dict[str, str]:
    return {a: spec.name for a, spec in ALGOS.items()}


def pick(regime: RegimeResult, table: dict[str, Any] | None = None) -> dict[str, Any]:
    table = table if table is not None else load_table()
    return chooser.choose(
        regime.label, regime.confidence, table, names(), candidates=candidate_ids()
    )


def smart_plan(
    regime: RegimeResult,
    *,
    capital: float,
    lot_size: int,
    days_to_expiry: int | None,
    max_loss_pct: float | None = None,
    inputs: Any = None,
) -> Plan:
    """Run whichever algo the chooser picks for today, or sit out. Never invents its own trade."""
    decision = pick(regime)
    if decision["pick"] is None:
        return Plan(SMART_PICK, "skip", decision["headline"], None, 0, None, None)
    chosen = build(
        decision["pick"],
        regime,
        capital=capital,
        lot_size=lot_size,
        days_to_expiry=days_to_expiry,
        max_loss_pct=max_loss_pct,
        inputs=inputs,
    )
    if chosen.action != "trade":
        return Plan(
            SMART_PICK,
            "skip",
            f"Picked {ALGOS[decision['pick']].name}, which stood aside: {chosen.reason}",
            None,
            0,
            None,
            None,
        )
    return Plan(
        SMART_PICK,
        "trade",
        f"Picked {ALGOS[decision['pick']].name}. {chosen.reason}",
        chosen.config,
        chosen.lots,
        chosen.max_loss_inr,
        chosen.side,
    )
