# blueprints/algos.py
"""HTTP surface for the regime algo catalogue (session cookie, like /strategy).

The catalogue lists the algos, the market regime right now, and what the trader
has deployed. Deploying creates a Sandbox-only strategy; going Live is a
separate call that needs the trader to type back the worst-case loss in rupees.
Nothing here places an order: orders belong to ``services/strategy_module/``.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from flask import Blueprint, jsonify, request, session

from database import algo_db
from database import strategy_module_db as sm_store
from limiter import limiter
from services.algos import lab, runner
from services.algos.templates import ALGOS
from services.algos.templates import coverage as coverage_matrix
from utils.logging import get_logger
from utils.session import check_session_validity
from utils.thread_safe_cache import LockedTTLCache

logger = get_logger(__name__)

algos_bp = Blueprint("algos_bp", __name__, url_prefix="/algos")

ALGOS_RATE_LIMIT = os.getenv("STRATEGY_RATE_LIMIT", "200 per minute")
_api_limit = limiter.shared_limit(ALGOS_RATE_LIMIT, scope="algos_api")

MIN_CAPITAL = 10_000
MAX_CAPITAL = 1_000_000_000

#: Gathering the regime makes several outbound calls, so one snapshot is shared
#: for a minute instead of being rebuilt on every page refresh.
_regime_cache = LockedTTLCache(maxsize=8, ttl=60)

#: Replays are CPU work and the first one downloads history, so they get a tighter
#: limit than the rest of the page, and results are cached for a few minutes.
_lab_limit = limiter.shared_limit("12 per minute", scope="algos_lab")
_history_cache = LockedTTLCache(maxsize=1, ttl=3600)
_lab_cache = LockedTTLCache(maxsize=32, ttl=600)
LAB_FIRST_YEAR = 2015

NOT_FOUND = "Algo not found"


def _user() -> str | None:
    return session.get("user")


def _ok(payload: dict | None = None, code: int = 200):
    body: dict[str, Any] = {"status": "success"}
    if payload:
        body.update(payload)
    return jsonify(body), code


def _error(message: str, code: int, payload: dict | None = None):
    body: dict[str, Any] = {"status": "error", "message": message}
    if payload:
        body.update(payload)
    return jsonify(body), code


def _body() -> tuple[dict | None, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _error("The request body must be a JSON object", 400)
    return data, None


def _capital(value: Any) -> tuple[float | None, str | None]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, "capital must be a number"
    if not (MIN_CAPITAL <= value <= MAX_CAPITAL):
        return None, f"capital must be between {MIN_CAPITAL:,} and {MAX_CAPITAL:,} rupees"
    return float(value), None


def _spec(algo_id: str) -> dict[str, Any]:
    spec = ALGOS[algo_id]
    return {
        "id": spec.id,
        "name": spec.name,
        "summary": spec.summary,
        "risk": spec.risk,
        "allowed_regimes": list(spec.allowed_labels),
        "overnight": spec.overnight,
        "entry_time": spec.entry_time,
        "status": spec.status,
        "evidence": spec.evidence,
    }


def _deployment_view(dep: dict, *, decisions: int = 5) -> dict[str, Any]:
    row = sm_store.get_strategy(dep["strategy_id"], dep["user_id"])
    view = {k: v for k, v in dep.items() if k != "user_id"}
    view["live_enabled"] = bool(row.live_enabled) if row else False
    view["position_open"] = bool(row and row.status == "running")
    view["max_loss_ceiling_inr"] = runner.max_loss_ceiling(dep["algo_id"], dep["capital"])
    view["recent_decisions"] = algo_db.list_decisions(dep["id"], decisions)
    view["live_gate"] = runner.live_gate(dep["strategy_id"])
    return view


def _mine(deployment_id: int):
    user = _user()
    dep = algo_db.get_deployment(deployment_id, user) if user else None
    return user, dep


@algos_bp.errorhandler(429)
def _rate_limited(error):
    response = jsonify(
        {
            "status": "error",
            "result": "rate_limited",
            "message": "Too many requests. Please slow down.",
        }
    )
    response.status_code = 429
    return response


@algos_bp.route("/api/catalogue", methods=["GET"])
@check_session_validity
@_api_limit
def catalogue():
    user = _user()
    if not user:
        return _error("Not authenticated", 401)
    deployed = {d["algo_id"]: d for d in algo_db.list_deployments(user)}
    items = []
    for algo_id in ALGOS:
        item = _spec(algo_id)
        dep = deployed.get(algo_id)
        item["deployment"] = _deployment_view(dep) if dep else None
        items.append(item)
    return _ok({"data": items})


@algos_bp.route("/api/regime", methods=["GET"])
@check_session_validity
@_api_limit
def regime():
    user = _user()
    if not user:
        return _error("Not authenticated", 401)
    api_key = runner._api_key(user)
    if not api_key:
        return _error("No OpenAlgo API key found. Generate one on the API Key page.", 400)

    def load():
        result, _ = runner.current_regime(api_key)
        return runner.regime_to_dict(result)

    return _ok({"data": _regime_cache.get_or_load(user, load)})


@algos_bp.route("/api/coverage", methods=["GET"])
@check_session_validity
@_api_limit
def coverage():
    """Which algos trade in which regimes, and the days the platform stands aside."""
    if not _user():
        return _error("Not authenticated", 401)
    return _ok({"data": coverage_matrix()})


def _lab_date(value: Any, label: str) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, None
    if not isinstance(value, str):
        return None, f"{label} must be a date like 2023-01-31"
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None, f"{label} must be a date like 2023-01-31"
    if not (LAB_FIRST_YEAR <= parsed.year <= date.today().year):
        return None, f"{label} must be between {LAB_FIRST_YEAR} and this year"
    return parsed.isoformat(), None


@algos_bp.route("/api/lab/run", methods=["POST"])
@check_session_validity
@_lab_limit
def lab_run():
    """Replay an algo over real history, with no broker. Nothing is traded or saved."""
    if not _user():
        return _error("Not authenticated", 401)
    data, error = _body()
    if error:
        return error
    algo_id = data.get("algo_id")
    if algo_id not in ALGOS:
        return _error("Unknown algo", 400)
    model = data.get("model", "conservative")
    if model not in lab.MODELS:
        return _error("model must be standard or conservative", 400)
    gated = data.get("gated", True)
    if not isinstance(gated, bool):
        return _error("gated must be true or false", 400)
    start, message = _lab_date(data.get("start"), "start")
    if message:
        return _error(message, 400)
    end, message = _lab_date(data.get("end"), "end")
    if message:
        return _error(message, 400)
    if start and end and start > end:
        return _error("start must be before end", 400)

    key = (algo_id, model, gated, start, end)

    def run():
        history = _history_cache.get_or_load("history", lab.load_history)
        result = lab.run_lab(history, algo_id, start=start, end=end, model=model, gated=gated)
        return lab.to_payload(result, gated=gated)

    try:
        payload = _lab_cache.get_or_load(key, run)
    except lab.HistoryUnavailable as exc:
        return _error(str(exc), 503)
    except Exception:
        logger.exception("Lab run failed for %s", key)
        return _error("The Lab could not finish this run. Nothing was changed. Try again.", 500)
    return _ok({"data": payload})


@algos_bp.route("/api/preview", methods=["POST"])
@check_session_validity
@_api_limit
def preview():
    user = _user()
    if not user:
        return _error("Not authenticated", 401)
    data, error = _body()
    if error:
        return error
    algo_id = data.get("algo_id")
    if algo_id not in ALGOS:
        return _error("Unknown algo", 400)
    capital, message = _capital(data.get("capital"))
    if message:
        return _error(message, 400)
    api_key = runner._api_key(user)
    if not api_key:
        return _error("No OpenAlgo API key found. Generate one on the API Key page.", 400)
    return _ok({"data": runner.preview(algo_id, capital, api_key)})


@algos_bp.route("/api/deployments", methods=["POST"])
@check_session_validity
@_api_limit
def deploy():
    user = _user()
    if not user:
        return _error("Not authenticated", 401)
    data, error = _body()
    if error:
        return error
    algo_id = data.get("algo_id")
    if algo_id not in ALGOS:
        return _error("Unknown algo", 400)
    capital, message = _capital(data.get("capital"))
    if message:
        return _error(message, 400)
    dep, message = runner.deploy(user, algo_id, capital)
    if not dep:
        code = 409 if message and "already" in message else 400
        return _error(message or "Could not deploy", code)
    return _ok({"data": _deployment_view(dep)}, 201)


@algos_bp.route("/api/deployments/<int:deployment_id>", methods=["GET"])
@check_session_validity
@_api_limit
def get_deployment(deployment_id):
    user, dep = _mine(deployment_id)
    if not user:
        return _error("Not authenticated", 401)
    if not dep:
        return _error(NOT_FOUND, 404)
    return _ok({"data": _deployment_view(dep, decisions=60)})


@algos_bp.route("/api/deployments/<int:deployment_id>/active", methods=["POST"])
@check_session_validity
@_api_limit
def set_active(deployment_id):
    user, dep = _mine(deployment_id)
    if not user:
        return _error("Not authenticated", 401)
    if not dep:
        return _error(NOT_FOUND, 404)
    data, error = _body()
    if error:
        return error
    if not isinstance(data.get("active"), bool):
        return _error("active must be true or false", 400)
    updated = algo_db.update_deployment(deployment_id, user, active=data["active"])
    if not updated:
        return _error("Could not update the algo", 500)
    runner.sync_job(deployment_id)
    return _ok({"data": _deployment_view(updated)})


@algos_bp.route("/api/deployments/<int:deployment_id>/live", methods=["POST"])
@check_session_validity
@_api_limit
def set_live(deployment_id):
    """Switch between Sandbox and Live.

    Going Live needs ``confirm_max_loss`` equal to the worst-case loss in
    rupees that the page showed, so the trader has read the number.
    """
    user, dep = _mine(deployment_id)
    if not user:
        return _error("Not authenticated", 401)
    if not dep:
        return _error(NOT_FOUND, 404)
    data, error = _body()
    if error:
        return error
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        return _error("enabled must be true or false", 400)

    row = sm_store.get_strategy(dep["strategy_id"], user)
    if row is None:
        return _error("The strategy behind this algo is missing", 500)
    if row.status == "running":
        return _error("Wait for the open position to close before changing the mode.", 409)

    if enabled:
        gate = runner.live_gate(dep["strategy_id"])
        if not gate["allowed"]:
            return _error(gate["reason"], 403, {"live_gate": gate})
        ceiling = runner.max_loss_ceiling(dep["algo_id"], dep["capital"])
        confirm = data.get("confirm_max_loss")
        if ceiling is None:
            return _error("The worst-case loss could not be worked out. Try again shortly.", 503)
        if isinstance(confirm, bool) or not isinstance(confirm, (int, float)):
            return _error(
                f"Type back the worst-case loss of {ceiling:,.0f} rupees to go Live.",
                400,
                {"max_loss_ceiling_inr": ceiling},
            )
        if abs(float(confirm) - ceiling) > 1:
            return _error(
                f"That does not match the worst-case loss of {ceiling:,.0f} rupees.",
                400,
                {"max_loss_ceiling_inr": ceiling},
            )

    changed, message = sm_store.set_live_enabled(dep["strategy_id"], user, enabled)
    if not changed:
        return _error(message or "Could not change the mode", 409)
    updated = algo_db.update_deployment(deployment_id, user, mode="live" if enabled else "sandbox")
    if not updated:
        return _error("Could not update the algo", 500)
    return _ok({"data": _deployment_view(updated)})


@algos_bp.route("/api/deployments/<int:deployment_id>/run-now", methods=["POST"])
@check_session_validity
@_api_limit
def run_now(deployment_id):
    """Run today's entry check immediately, in the algo's current mode."""
    user, dep = _mine(deployment_id)
    if not user:
        return _error("Not authenticated", 401)
    if not dep:
        return _error(NOT_FOUND, 404)
    if not dep["active"]:
        return _error("Turn the algo on first.", 409)
    outcome = runner.run_entry(deployment_id)
    return _ok({"data": outcome, "deployment": _deployment_view(dep)})


@algos_bp.route("/api/deployments/<int:deployment_id>", methods=["DELETE"])
@check_session_validity
@_api_limit
def remove(deployment_id):
    user, dep = _mine(deployment_id)
    if not user:
        return _error("Not authenticated", 401)
    if not dep:
        return _error(NOT_FOUND, 404)
    ok, message = runner.remove(deployment_id, user)
    if not ok:
        return _error(message or "Could not remove the algo", 409)
    return _ok()
