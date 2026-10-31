"""HTTP surface for the Research page: the cross-market linkage study (session cookie, like /algos).

Serves docs/algos/research/linkage.json, which scripts/algo_backtest/export_linkage_graph.py writes
from the study tables. Statistics only; it reads one file and calls no broker.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, session

from limiter import limiter
from utils.logging import get_logger
from utils.session import check_session_validity

logger = get_logger(__name__)

research_bp = Blueprint("research_bp", __name__, url_prefix="/research")

RESEARCH_RATE_LIMIT = os.getenv("STRATEGY_RATE_LIMIT", "200 per minute")
_api_limit = limiter.shared_limit(RESEARCH_RATE_LIMIT, scope="research_api")

LINKAGE_FILE = Path(__file__).resolve().parents[1] / "docs" / "algos" / "research" / "linkage.json"


def _load_linkage() -> dict | None:
    try:
        return json.loads(LINKAGE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        logger.exception("Could not read the linkage results file")
        return None


@research_bp.route("/api/linkage", methods=["GET"])
@check_session_validity
@_api_limit
def linkage():
    if not session.get("user"):
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    data = _load_linkage()
    if data is None:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "The research results are not in this copy of OpenAlgo yet. "
                    "Update OpenAlgo to the latest version and open this page again.",
                }
            ),
            404,
        )
    return jsonify({"status": "success", "data": data})
