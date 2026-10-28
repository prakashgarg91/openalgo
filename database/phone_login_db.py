# database/phone_login_db.py
"""The one phone number allowed to sign in to this installation.

OpenAlgo has a single user, so this is one row at most per user. The number is
stored in the clear because the server has to text it; the codes are never stored
here (see ``services/phone/otp.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

from database.engine_factory import create_db_engine
from utils.logging import get_logger

logger = get_logger(__name__)

engine = create_db_engine()
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()


class PhoneLogin(Base):
    __tablename__ = "phone_login"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(80), nullable=False, unique=True)
    phone = Column(String(20), nullable=False, unique=True)
    verified_at = Column(DateTime, nullable=False)


def init_db() -> None:
    logger.debug("Initializing Phone Login DB")
    Base.metadata.create_all(bind=engine)


def get_phone(user_id: str) -> str | None:
    row = PhoneLogin.query.filter_by(user_id=user_id).first()
    return row.phone if row else None


def find_user_for_phone(phone: str) -> str | None:
    row = PhoneLogin.query.filter_by(phone=phone).first()
    return row.user_id if row else None


def set_phone(user_id: str, phone: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        row = PhoneLogin.query.filter_by(user_id=user_id).first()
        if row:
            row.phone, row.verified_at = phone, now
        else:
            db_session.add(PhoneLogin(user_id=user_id, phone=phone, verified_at=now))
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise


def clear_phone(user_id: str) -> None:
    try:
        PhoneLogin.query.filter_by(user_id=user_id).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
