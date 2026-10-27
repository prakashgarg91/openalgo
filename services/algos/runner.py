"""Orchestration for deployed algos: deploy, daily entry check, scheduling.

The only module in ``services/algos/`` that touches the database, the broker
and the engine. The decisions themselves come from ``context`` and
``templates``, which stay pure. Orders, stops, recovery and the Sandbox/Live
rule belong to ``services/strategy_module/``; this module configures a normal
strategy and starts a normal run.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from database import algo_db
from database import strategy_module_db as sm_store
from services.algos import inputs as feed
from services.algos.context import RegimeResult, score_regime
from services.algos.templates import ALGOS, Plan, build
from utils.db_sessions import releases_scoped_sessions
from utils.logging import get_logger

logger = get_logger(__name__)

ENTRY_HOUR = 15
ENTRY_MINUTE = 5
JOB_PREFIX = "algo:"
FALLBACK_LOT_SIZE_KEY = "NIFTY"

#: A neutral, calm regime used only to shape the strategy row at deploy time.
#: Every real entry replaces the legs from a fresh regime.
_PLACEHOLDER_REGIME = RegimeResult(
    label="calm", bias="neutral", score=0.0, confidence=1.0, reasons=(), missing=()
)


def regime_to_dict(regime: RegimeResult) -> dict[str, Any]:
    return {
        "label": regime.label,
        "bias": regime.bias,
        "score": regime.score,
        "confidence": regime.confidence,
        "reasons": list(regime.reasons),
        "missing": list(regime.missing),
    }


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return {
        "algo_id": plan.algo_id,
        "action": plan.action,
        "reason": plan.reason,
        "lots": plan.lots,
        "max_loss_inr": plan.max_loss_inr,
        "side": plan.side,
    }


def nifty_lot_size() -> int | None:
    """The current NIFTY option lot size from the symbol master, or None."""
    try:
        from database.symbol import SymToken, db_session

        row = (
            db_session.query(SymToken.lotsize)
            .filter(
                SymToken.name == "NIFTY",
                SymToken.exchange == "NFO",
                SymToken.instrumenttype == "CE",
                SymToken.lotsize > 0,
            )
            .first()
        )
        return int(row[0]) if row and row[0] else None
    except Exception:
        logger.exception("Could not read the NIFTY lot size")
        return None


def days_to_expiry(api_key: str, today: date | None = None) -> int | None:
    """Calendar days from today to the nearest NIFTY weekly expiry, or None."""
    from services.expiry_service import get_expiry_dates

    today = today or date.today()
    try:
        ok, response, _ = get_expiry_dates("NIFTY", "NFO", "options", api_key)
    except Exception:
        logger.exception("Could not read NIFTY expiries")
        return None
    if not ok:
        return None
    for text in response.get("data") or []:
        for fmt in ("%d-%b-%y", "%d-%b-%Y"):
            try:
                return (datetime.strptime(text, fmt).date() - today).days
            except ValueError:
                continue
    return None


def current_regime(api_key: str) -> tuple[RegimeResult, feed.MarketInputs]:
    snapshot = feed.collect(api_key)
    return score_regime(snapshot), snapshot


def _api_key(user_id: str) -> str | None:
    from services.strategy_module.engine import _api_key_for

    return _api_key_for(user_id)


def _is_holiday(day: date) -> bool:
    try:
        from database.market_calendar_db import is_market_holiday

        return bool(is_market_holiday(day, "NFO"))
    except Exception:
        logger.exception("Could not check the market calendar")
        return False


def max_loss_ceiling(algo_id: str, capital: float) -> float | None:
    """The worst-case rupee loss this algo can be sized to at this capital.

    Shown to the trader before Live and typed back to confirm. It comes from the
    same sizing rule the entry uses, so the number they confirm is the one the
    algo will not exceed.
    """
    lot = nifty_lot_size()
    if lot is None or algo_id not in ALGOS:
        return None
    plan = build(algo_id, _PLACEHOLDER_REGIME, capital=capital, lot_size=lot, days_to_expiry=4)
    return plan.max_loss_inr


def preview(
    algo_id: str, capital: float, api_key: str, *, max_loss_pct: float | None = None
) -> dict[str, Any]:
    """What the algo would do right now, without saving or starting anything."""
    regime, _ = current_regime(api_key)
    lot = nifty_lot_size()
    if lot is None:
        return {
            "regime": regime_to_dict(regime),
            "plan": {
                "algo_id": algo_id,
                "action": "skip",
                "reason": "The Nifty lot size is not available. Download the master contract first.",
                "lots": 0,
                "max_loss_inr": None,
                "side": None,
            },
        }
    kwargs = {} if max_loss_pct is None else {"max_loss_pct": max_loss_pct}
    plan = build(
        algo_id,
        regime,
        capital=capital,
        lot_size=lot,
        days_to_expiry=days_to_expiry(api_key),
        **kwargs,
    )
    return {"regime": regime_to_dict(regime), "plan": plan_to_dict(plan)}


def deploy(user_id: str, algo_id: str, capital: float) -> tuple[dict | None, str | None]:
    """Create the strategy row and the deployment. Born Stopped, in Sandbox."""
    from blueprints.strategy_module import validate_strategy_config

    if algo_id not in ALGOS:
        return None, "Unknown algo"
    lot = nifty_lot_size()
    if lot is None:
        return None, "The Nifty lot size is not available. Download the master contract first."

    plan = build(algo_id, _PLACEHOLDER_REGIME, capital=capital, lot_size=lot, days_to_expiry=4)
    if plan.action != "trade":
        return None, plan.reason

    shell = dict(plan.config)
    shell["name"] = f"{ALGOS[algo_id].name} (algo)"
    config, error = validate_strategy_config(shell)
    if error:
        return None, error

    created, message = sm_store.create_strategy(user_id, config)
    if not created:
        return None, message or "Could not create the strategy"
    created.pop("webhook_token", None)

    deployment, message = algo_db.create_deployment(user_id, algo_id, created["id"], capital)
    if not deployment:
        sm_store.delete_strategy(created["id"], user_id)
        return None, message
    _sync_strategy_jobs(created["id"])
    return deployment, None


def remove(deployment_id: int, user_id: str) -> tuple[bool, str | None]:
    dep = algo_db.get_deployment(deployment_id, user_id)
    if not dep:
        return False, "Deployment not found"
    row = sm_store.get_strategy(dep["strategy_id"], user_id)
    if row is not None and row.status == "running":
        return False, "Stop the running position before removing this algo."
    remove_job(deployment_id)
    if not algo_db.delete_deployment(deployment_id, user_id):
        return False, "Could not remove the algo"
    sm_store.delete_strategy(dep["strategy_id"], user_id)
    _sync_strategy_jobs(dep["strategy_id"], removed=True)
    return True, None


def _sync_strategy_jobs(strategy_id: int, *, removed: bool = False) -> None:
    """Install (or drop) the strategy's own 09:45 square-off job.

    The strategy row is written straight to the store, not through the
    /strategy API that normally syncs the schedule, so it is done here.
    """
    from services.strategy_module import scheduler

    try:
        if removed:
            scheduler.remove_strategy_jobs(strategy_id)
        else:
            scheduler.sync_strategy_jobs(strategy_id)
    except Exception:
        logger.exception("Could not sync the schedule for strategy %s", strategy_id)


def _record(dep_id: int, action: str, reason: str, **fields: Any) -> dict[str, Any]:
    algo_db.record_decision(dep_id, action, reason, **fields)
    return {"action": action, "reason": reason, **fields}


@releases_scoped_sessions
def run_entry(deployment_id: int, *, today: date | None = None) -> dict[str, Any]:
    """The daily entry check for one deployment.

    Scores the market on fresh data, builds the plan, and either records why it
    is standing aside or configures and starts a run. Never raises: a failure
    is recorded as an error decision so the trader sees it.
    """
    today = today or date.today()
    dep = algo_db.get_deployment(deployment_id)
    if not dep or not dep["active"]:
        return {"action": "skip", "reason": "Not active"}
    user_id = dep["user_id"]

    try:
        if _is_holiday(today):
            return _record(deployment_id, "skip", "The market is closed today.")

        row = sm_store.get_strategy(dep["strategy_id"], user_id)
        if row is None:
            return _record(deployment_id, "error", "The strategy behind this algo is missing.")
        if row.status == "running":
            return _record(
                deployment_id,
                "skip",
                "The previous position is still open, so no new one was started.",
            )

        api_key = _api_key(user_id)
        if not api_key:
            return _record(
                deployment_id,
                "error",
                "No OpenAlgo API key found. Generate one on the API Key page.",
            )

        regime, _ = current_regime(api_key)
        regime_fields = {
            "regime_label": regime.label,
            "bias": regime.bias,
            "confidence": regime.confidence,
            "detail": {"reasons": list(regime.reasons), "missing": list(regime.missing)},
        }

        lot = nifty_lot_size()
        if lot is None:
            return _record(
                deployment_id,
                "error",
                "The Nifty lot size is not available. Download the master contract first.",
                **regime_fields,
            )

        plan = build(
            dep["algo_id"],
            regime,
            capital=dep["capital"],
            lot_size=lot,
            days_to_expiry=days_to_expiry(api_key, today),
        )
        if plan.action != "trade":
            return _record(deployment_id, "skip", plan.reason, **regime_fields)

        from blueprints.strategy_module import validate_strategy_config
        from services.strategy_module import engine

        shell = dict(plan.config)
        shell["name"] = row.name
        config, error = validate_strategy_config(shell)
        if error:
            return _record(deployment_id, "error", error, **regime_fields)

        updated, message = sm_store.update_strategy(
            dep["strategy_id"],
            user_id,
            {"legs": config["legs"], "daily_loss_limit_inr": config["daily_loss_limit_inr"]},
        )
        if not updated:
            return _record(
                deployment_id, "error", message or "Could not set the legs", **regime_fields
            )

        result = engine.start_run(
            dep["strategy_id"], user_id, dep["mode"], trigger_source="scheduler"
        )
        fields = {
            **regime_fields,
            "side": plan.side,
            "lots": plan.lots,
            "max_loss_inr": plan.max_loss_inr,
        }
        if not result.ok:
            return _record(
                deployment_id,
                "error",
                result.error or "The run could not be started.",
                **fields,
            )
        return _record(deployment_id, "trade", plan.reason, run_id=result.run_id, **fields)
    except Exception:
        logger.exception("Entry check failed for deployment %s", deployment_id)
        return _record(
            deployment_id, "error", "The entry check failed. It will try again tomorrow."
        )


# ---------------------------------------------------------------------------
# Scheduling: one cron job per active deployment, on the strategy scheduler.
# ---------------------------------------------------------------------------


def job_id(deployment_id: int) -> str:
    return f"{JOB_PREFIX}{deployment_id}:entry"


def sync_job(deployment_id: int) -> bool:
    """Install or remove the daily entry job to match the deployment's state."""
    from apscheduler.triggers.cron import CronTrigger

    from services.strategy_module import scheduler

    sched = scheduler.get_scheduler()
    if sched is None:
        return False
    dep = algo_db.get_deployment(deployment_id)
    if not dep or not dep["active"]:
        remove_job(deployment_id)
        return True
    sched.add_job(
        func=run_entry,
        args=[deployment_id],
        trigger=CronTrigger(
            day_of_week="mon-fri", hour=ENTRY_HOUR, minute=ENTRY_MINUTE, timezone=scheduler.IST
        ),
        id=job_id(deployment_id),
        name=f"Algo {deployment_id} daily entry check",
        replace_existing=True,
    )
    return True


def remove_job(deployment_id: int) -> None:
    from services.strategy_module import scheduler

    sched = scheduler.get_scheduler()
    if sched is None:
        return
    try:
        sched.remove_job(job_id(deployment_id))
    except Exception:
        pass


@releases_scoped_sessions
def sync_all_jobs() -> int:
    """Rebuild every entry job from the database. Called once after the scheduler starts.

    Runs on the boot thread, where no request teardown fires, so it releases
    its own sessions.
    """
    count = 0
    for dep in algo_db.list_deployments(active_only=True):
        if sync_job(dep["id"]):
            count += 1
    return count
