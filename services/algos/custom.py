"""Putting algos the trader built into the live catalogue.

A built algo is stored as a row, and shows up in ``ALGOS`` as ``custom_<id>`` so the
catalogue, the Sandbox-first deploy, the daily runner and the Live gate treat it
exactly like a shipped one. It is always marked experimental.
"""

from __future__ import annotations

from typing import Any

from services.algos import builder
from services.algos.templates import ALGOS, CUSTOM_SPECS, AlgoSpec
from utils.logging import get_logger

logger = get_logger(__name__)


def algo_id(row_id: int) -> str:
    return f"custom_{row_id}"


def register(row: dict[str, Any]) -> str:
    spec = builder.Spec.from_dict(row["spec"])
    key = algo_id(row["id"])
    ALGOS[key] = AlgoSpec(
        id=key,
        name=row["name"],
        summary=f"Built by you: {spec.name}. Sandbox first, like every algo.",
        risk="medium",
        allowed_labels=spec.labels,
        min_confidence=builder.MIN_CONFIDENCE,
        overnight=True,
        status="experimental",
        evidence=row.get("evidence", ""),
    )
    CUSTOM_SPECS[key] = spec
    return key


def unregister(row_id: int) -> None:
    key = algo_id(row_id)
    ALGOS.pop(key, None)
    CUSTOM_SPECS.pop(key, None)


def register_saved() -> int:
    """Load every stored algo. A row that no longer validates is skipped, not fatal."""
    from database import algo_db

    count = 0
    for row in algo_db.list_custom():
        try:
            register(row)
            count += 1
        except Exception:
            logger.exception("Could not load built algo %s", row.get("id"))
    return count
