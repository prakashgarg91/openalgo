# database/algo_db.py
"""Persistence for the regime algo catalogue.

Two tables. ``algo_deployment`` is one algo a trader switched on, tied to the
``sm_strategy`` row that actually trades it. ``algo_decision`` is the append-only
log of what the algo decided each day and why, which is also the track record
the catalogue shows before anything goes Live.

This module does no validation of trading configuration. The strategy row is
created and edited through ``database.strategy_module_db``, whose API boundary
validator stands between a payload and an order.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

from database.engine_factory import create_db_engine
from utils.logging import get_logger

logger = get_logger(__name__)

engine = create_db_engine()
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

#: Decisions kept per deployment. The log is for the trader to read and for the
#: track record, not an archive, and a process that never restarts must not
#: grow it forever.
MAX_DECISIONS_PER_DEPLOYMENT = 400
DECISION_ACTIONS = ("trade", "skip", "error")
DEPLOYMENT_MODES = ("sandbox", "live")


def utcnow() -> datetime:
    """Naive UTC, matching the other strategy tables."""
    return datetime.now(UTC).replace(tzinfo=None)


class AlgoDeployment(Base):
    __tablename__ = "algo_deployment"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(80), nullable=False, index=True)
    algo_id = Column(String(40), nullable=False)
    # Plain integer, not a foreign key, for the same SQLite reason as
    # sm_strategy.current_run_id.
    strategy_id = Column(Integer, nullable=False, index=True)
    capital = Column(Numeric(18, 2), nullable=False)
    # Active means the daily entry check runs. Stopped means it does not.
    active = Column(Boolean, nullable=False, default=False)
    mode = Column(String(10), nullable=False, default="sandbox")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "algo_id", name="uq_algo_deployment_user_algo"),)


class AlgoCustom(Base):
    """An algo the trader built with the builder. Its id as a catalogue entry is ``custom_<id>``."""

    __tablename__ = "algo_custom"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(80), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    spec = Column(JSON, nullable=False)
    evidence = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=utcnow)


class AlgoDecision(Base):
    __tablename__ = "algo_decision"

    id = Column(Integer, primary_key=True)
    deployment_id = Column(Integer, nullable=False, index=True)
    decided_at = Column(DateTime, nullable=False, default=utcnow)
    action = Column(String(10), nullable=False)
    regime_label = Column(String(20), nullable=True)
    bias = Column(String(10), nullable=True)
    confidence = Column(Numeric(6, 4), nullable=True)
    side = Column(String(10), nullable=True)
    lots = Column(Integer, nullable=True)
    max_loss_inr = Column(Numeric(18, 2), nullable=True)
    run_id = Column(Integer, nullable=True)
    reason = Column(Text, nullable=False, default="")
    detail = Column(JSON, nullable=True)

    __table_args__ = (Index("ix_algo_decision_dep_time", "deployment_id", "decided_at"),)


def init_db() -> None:
    """Create the algo tables if they do not exist."""
    logger.debug("Initializing Algo DB")
    Base.metadata.create_all(bind=engine)


def _deployment_dict(row: AlgoDeployment) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "algo_id": row.algo_id,
        "strategy_id": row.strategy_id,
        "capital": float(row.capital),
        "active": bool(row.active),
        "mode": row.mode,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _decision_dict(row: AlgoDecision) -> dict[str, Any]:
    return {
        "id": row.id,
        "deployment_id": row.deployment_id,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "action": row.action,
        "regime_label": row.regime_label,
        "bias": row.bias,
        "confidence": float(row.confidence) if row.confidence is not None else None,
        "side": row.side,
        "lots": row.lots,
        "max_loss_inr": float(row.max_loss_inr) if row.max_loss_inr is not None else None,
        "run_id": row.run_id,
        "reason": row.reason,
        "detail": row.detail,
    }


def create_deployment(
    user_id: str, algo_id: str, strategy_id: int, capital: float
) -> tuple[dict | None, str | None]:
    """A new deployment, born Stopped and in Sandbox mode."""
    try:
        existing = (
            db_session.query(AlgoDeployment).filter_by(user_id=user_id, algo_id=algo_id).first()
        )
        if existing:
            return None, "This algo is already deployed. Remove it first to deploy it again."
        row = AlgoDeployment(
            user_id=user_id,
            algo_id=algo_id,
            strategy_id=strategy_id,
            capital=capital,
            active=False,
            mode="sandbox",
        )
        db_session.add(row)
        db_session.commit()
        return _deployment_dict(row), None
    except Exception:
        db_session.rollback()
        logger.exception("Could not create the %s deployment for %s", algo_id, user_id)
        return None, "Could not save the deployment"


def get_deployment(deployment_id: int, user_id: str | None = None) -> dict | None:
    """One deployment. ``user_id`` scopes it to its owner; the scheduler passes none."""
    try:
        query = db_session.query(AlgoDeployment).filter_by(id=deployment_id)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        row = query.first()
        return _deployment_dict(row) if row else None
    except Exception:
        logger.exception("Could not read deployment %s", deployment_id)
        return None


def list_deployments(user_id: str | None = None, *, active_only: bool = False) -> list[dict]:
    try:
        query = db_session.query(AlgoDeployment)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        if active_only:
            query = query.filter_by(active=True)
        return [_deployment_dict(r) for r in query.order_by(AlgoDeployment.id).all()]
    except Exception:
        logger.exception("Could not list deployments")
        return []


def update_deployment(deployment_id: int, user_id: str, **changes: Any) -> dict | None:
    """Change ``active``, ``mode`` or ``capital`` on one deployment."""
    allowed = {"active", "mode", "capital"}
    try:
        row = db_session.query(AlgoDeployment).filter_by(id=deployment_id, user_id=user_id).first()
        if not row:
            return None
        for field, value in changes.items():
            if field in allowed:
                setattr(row, field, value)
        db_session.commit()
        return _deployment_dict(row)
    except Exception:
        db_session.rollback()
        logger.exception("Could not update deployment %s", deployment_id)
        return None


def delete_deployment(deployment_id: int, user_id: str) -> bool:
    """Remove a deployment and its decision log. The strategy row is left to the caller."""
    try:
        row = db_session.query(AlgoDeployment).filter_by(id=deployment_id, user_id=user_id).first()
        if not row:
            return False
        db_session.query(AlgoDecision).filter_by(deployment_id=deployment_id).delete()
        db_session.delete(row)
        db_session.commit()
        return True
    except Exception:
        db_session.rollback()
        logger.exception("Could not delete deployment %s", deployment_id)
        return False


def record_decision(deployment_id: int, action: str, reason: str, **fields: Any) -> dict | None:
    """Append one decision and trim the log to its cap."""
    if action not in DECISION_ACTIONS:
        raise ValueError(f"action must be one of {DECISION_ACTIONS}")
    columns = {
        "regime_label",
        "bias",
        "confidence",
        "side",
        "lots",
        "max_loss_inr",
        "run_id",
        "detail",
    }
    try:
        row = AlgoDecision(
            deployment_id=deployment_id,
            action=action,
            reason=reason,
            **{k: v for k, v in fields.items() if k in columns},
        )
        db_session.add(row)
        db_session.commit()
        _trim(deployment_id)
        return _decision_dict(row)
    except Exception:
        db_session.rollback()
        logger.exception("Could not record a decision for deployment %s", deployment_id)
        return None


def _trim(deployment_id: int) -> None:
    try:
        keep = (
            db_session.query(AlgoDecision.id)
            .filter_by(deployment_id=deployment_id)
            .order_by(AlgoDecision.id.desc())
            .offset(MAX_DECISIONS_PER_DEPLOYMENT)
            .first()
        )
        if keep:
            db_session.query(AlgoDecision).filter(
                AlgoDecision.deployment_id == deployment_id, AlgoDecision.id <= keep[0]
            ).delete(synchronize_session=False)
            db_session.commit()
    except Exception:
        db_session.rollback()
        logger.exception("Could not trim the decision log for deployment %s", deployment_id)


def list_decisions(deployment_id: int, limit: int = 60) -> list[dict]:
    try:
        rows = (
            db_session.query(AlgoDecision)
            .filter_by(deployment_id=deployment_id)
            .order_by(AlgoDecision.id.desc())
            .limit(max(1, min(limit, 400)))
            .all()
        )
        return [_decision_dict(r) for r in rows]
    except Exception:
        logger.exception("Could not read decisions for deployment %s", deployment_id)
        return []


def _custom_dict(row: AlgoCustom) -> dict[str, Any]:
    return {
        "id": row.id,
        "algo_id": f"custom_{row.id}",
        "user_id": row.user_id,
        "name": row.name,
        "spec": row.spec,
        "evidence": row.evidence,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


MAX_CUSTOM_PER_USER = 20


def create_custom(user_id: str, name: str, spec: dict[str, Any], evidence: str) -> dict[str, Any]:
    try:
        if AlgoCustom.query.filter_by(user_id=user_id).count() >= MAX_CUSTOM_PER_USER:
            raise ValueError(f"You can keep {MAX_CUSTOM_PER_USER} built algos. Delete one first.")
        row = AlgoCustom(user_id=user_id, name=name, spec=spec, evidence=evidence)
        db_session.add(row)
        db_session.commit()
        return _custom_dict(row)
    except Exception:
        db_session.rollback()
        raise


def list_custom(user_id: str | None = None) -> list[dict[str, Any]]:
    query = AlgoCustom.query
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    return [_custom_dict(r) for r in query.order_by(AlgoCustom.id).all()]


def get_custom(custom_id: int, user_id: str) -> dict[str, Any] | None:
    row = AlgoCustom.query.filter_by(id=custom_id, user_id=user_id).first()
    return _custom_dict(row) if row else None


def delete_custom(custom_id: int, user_id: str) -> bool:
    try:
        deleted = AlgoCustom.query.filter_by(id=custom_id, user_id=user_id).delete()
        db_session.commit()
        return bool(deleted)
    except Exception:
        db_session.rollback()
        raise
