"""The weekly housekeeping for the algo engines, started in its own process.

Once a week, outside market hours, it (1) rebuilds the chooser's evidence table if it is
older than a week, and (2) re-checks every algo the trader built against newer data and
stores a proposal if a different setup now looks better. It never applies a proposal.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from services.algos import builder_jobs, chooser_store, custom
from utils.logging import get_logger

logger = get_logger(__name__)

STALE_AFTER = timedelta(days=7)
JOB_ID = "algos_weekly_maintenance"
SYSTEM_USER = "system"


def table_is_stale(table: dict[str, Any] | None, now: datetime | None = None) -> bool:
    if not table or not table.get("built_at"):
        return True
    try:
        built = datetime.strptime(table["built_at"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=UTC)
    except ValueError:
        return True
    return (now or datetime.now(UTC)) - built > STALE_AFTER


def build_request(
    today: date, table: dict[str, Any] | None, now: datetime | None = None
) -> dict[str, Any]:
    customs = {a: spec.to_dict() for a, spec in custom.CUSTOM_SPECS.items()}
    ids = chooser_store.candidate_ids()
    chooser_customs = {a: customs[a] for a in ids if a in customs}
    return {
        "kind": "maintenance",
        "model": "conservative",
        "today": today.isoformat(),
        "rebuild_chooser": table_is_stale(table, now),
        "chooser": {
            "kind": "chooser",
            "algos": [a for a in ids if a not in chooser_customs],
            "customs": chooser_customs,
            "model": "conservative",
        },
        "customs": customs,
    }


def run_weekly(today: date | None = None) -> str | None:
    """Start the weekly pass. Returns the job id, or None when there is nothing to do."""
    request = build_request(today or date.today(), chooser_store.load_table())
    if not request["rebuild_chooser"] and not request["customs"]:
        return None
    try:
        return builder_jobs.start(SYSTEM_USER, request)
    except builder_jobs.Busy:
        logger.info("Weekly algo maintenance skipped: a search is already running")
        return None
    except Exception:
        logger.exception("Could not start the weekly algo maintenance")
        return None


def proposals() -> dict[str, Any]:
    try:
        return json.loads((builder_jobs.JOB_ROOT / "proposals.json").read_text())
    except (OSError, ValueError):
        return {}


def install_job() -> bool:
    """Schedule the weekly pass on the strategy scheduler: Sundays 10:00 IST."""
    from apscheduler.triggers.cron import CronTrigger

    from services.strategy_module import scheduler

    sched = scheduler.get_scheduler()
    if sched is None:
        return False
    sched.add_job(
        func=run_weekly,
        trigger=CronTrigger(day_of_week="sun", hour=10, minute=7, timezone=scheduler.IST),
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=6 * 3600,
        coalesce=True,
        max_instances=1,
    )
    return True
