# blueprints/phone_login.py
"""Sign in with the phone number registered on this installation.

Replaces the password as the first factor only. If the trader switched on an
authenticator code for login, that is still asked for afterwards; the broker login
that follows is untouched. The answer to "is this number registered?" is never
revealed to a caller who is not signed in: the response is the same either way.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, request, session

from database import phone_login_db as store
from limiter import limiter
from services.phone import otp, sender
from utils.ip_helper import get_real_ip
from utils.logging import get_logger
from utils.session import check_session_validity
from utils.thread_safe_cache import LockedTTLCache

logger = get_logger(__name__)

phone_bp = Blueprint("phone_bp", __name__, url_prefix="/auth/phone")

LOGIN_RATE_LIMIT_MIN = os.getenv("LOGIN_RATE_LIMIT_MIN", "5 per minute")
LOGIN_RATE_LIMIT_HOUR = os.getenv("LOGIN_RATE_LIMIT_HOUR", "25 per hour")

#: Live codes and send history. Bounded, and short-lived by construction.
_codes = LockedTTLCache(maxsize=2000, ttl=otp.TTL_SECONDS + 5)
_sends = LockedTTLCache(maxsize=2000, ttl=otp.HOUR + 5)
_fails = LockedTTLCache(maxsize=2000, ttl=otp.HOUR + 5)
_book = otp.OtpBook(os.getenv("APP_KEY", ""), _codes, _sends, time.time, _fails)

#: Texts are sent from here, not inside the request. If the request waited for the SMS
#: provider, a registered number would answer slower than an unregistered one, and the
#: difference in time would reveal which number belongs to this installation.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="phone-otp")

SENT = "If that number is registered, a code is on its way. It works for 5 minutes."
BAD_CODE = "That code is wrong or has expired. Ask for a new one."
NOT_SET_UP = (
    "Phone sign-in is not set up on this server. Add an SMS provider to your .env "
    "file (see docs/algos/phone-login.md), restart, and try again."
)


def _json():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _error(message: str, code: int, **extra):
    return jsonify({"status": "error", "message": message, **extra}), code


def _send_quietly(phone: str, code: str) -> None:
    try:
        sender.send(phone, code)
    except sender.SenderError as exc:
        logger.warning("Phone code not delivered: %s", exc)
    except Exception:
        logger.exception("Phone code delivery failed")


def _issue_and_maybe_send(purpose: str, phone: str, *, deliver: bool):
    """Throttle and mint a code the same way whether or not it will be sent."""
    issued = _book.issue(purpose, phone)
    if issued.code is None:
        return _error(
            f"Please wait {issued.retry_after} seconds before asking for another code.",
            429,
            retry_after=issued.retry_after,
        )
    if deliver and purpose == "register":
        # The trader is signed in and needs to know if the text did not go out.
        try:
            sender.send(phone, issued.code)
        except sender.SenderError as exc:
            logger.warning("Phone code not delivered: %s", exc)
            return _error(str(exc), 502)
    elif deliver:
        _executor.submit(_send_quietly, phone, issued.code)
    return jsonify({"status": "success", "message": SENT}), 200


@phone_bp.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "success", "enabled": sender.configured()})


@phone_bp.route("/request", methods=["POST"])
@limiter.limit(LOGIN_RATE_LIMIT_MIN)
@limiter.limit(LOGIN_RATE_LIMIT_HOUR)
def request_login_code():
    if not sender.configured():
        return _error(NOT_SET_UP, 400)
    phone = otp.normalise_phone(_json().get("phone"))
    if not phone:
        return _error("Enter a valid mobile number, for example 98765 43210.", 400)
    return _issue_and_maybe_send("login", phone, deliver=bool(store.find_user_for_phone(phone)))


@phone_bp.route("/verify", methods=["POST"])
@limiter.limit(LOGIN_RATE_LIMIT_MIN)
@limiter.limit(LOGIN_RATE_LIMIT_HOUR)
def verify_login_code():
    from blueprints.auth import _try_resume_broker_session, _utcnow_iso
    from database.auth_db import log_login_attempt
    from database.user_db import find_user_by_exact_username

    body = _json()
    phone = otp.normalise_phone(body.get("phone"))
    code = str(body.get("code", "")).strip()
    ip, ua = get_real_ip(), request.headers.get("User-Agent", "")
    username = store.find_user_for_phone(phone) if phone else None
    verdict = _book.verify("login", phone, code) if phone else otp.Verdict(False, "none")

    if not (verdict.ok and username):
        log_login_attempt(
            username or "unknown",
            ip,
            ua,
            status="failed",
            login_type="phone",
            failure_reason=f"phone_{verdict.reason}",
        )
        return _error(BAD_CODE, 401)

    session.clear()
    user = find_user_by_exact_username(username)
    if user is not None and user.is_totp_required_for("login"):
        session["pending_totp_user"] = username
        session["pending_totp_started_at"] = _utcnow_iso()
        return jsonify(
            {
                "status": "totp_required",
                "username": username,
                "message": "Enter the 6-digit code from your authenticator app.",
            }
        ), 200

    session["user"] = username
    resumed = _try_resume_broker_session(username)
    if resumed:
        log_login_attempt(
            username,
            ip,
            ua,
            status="success",
            login_type="phone_resume",
            broker=session.get("broker"),
        )
        return resumed
    log_login_attempt(username, ip, ua, status="success", login_type="phone")
    return jsonify({"status": "success"}), 200


# -- Registering the number, from inside a signed-in session ----------------


def _signed_in_user() -> str | None:
    return session.get("user") if session.get("logged_in") else None


@phone_bp.route("/me", methods=["GET"])
@check_session_validity
def my_phone():
    user = _signed_in_user()
    if not user:
        return _error("Not authenticated", 401)
    phone = store.get_phone(user)
    return jsonify(
        {
            "status": "success",
            "enabled": sender.configured(),
            "phone": otp.mask_phone(phone) if phone else None,
        }
    )


@phone_bp.route("/register/request", methods=["POST"])
@check_session_validity
@limiter.limit(LOGIN_RATE_LIMIT_MIN)
def register_request():
    if not _signed_in_user():
        return _error("Not authenticated", 401)
    if not sender.configured():
        return _error(NOT_SET_UP, 400)
    phone = otp.normalise_phone(_json().get("phone"))
    if not phone:
        return _error("Enter a valid mobile number, for example 98765 43210.", 400)
    return _issue_and_maybe_send("register", phone, deliver=True)


@phone_bp.route("/register/verify", methods=["POST"])
@check_session_validity
@limiter.limit(LOGIN_RATE_LIMIT_MIN)
def register_verify():
    user = _signed_in_user()
    if not user:
        return _error("Not authenticated", 401)
    body = _json()
    phone = otp.normalise_phone(body.get("phone"))
    verdict = (
        _book.verify("register", phone, str(body.get("code", "")).strip())
        if phone
        else otp.Verdict(False, "none")
    )
    if not verdict.ok:
        return _error(BAD_CODE, 400)
    store.set_phone(user, phone)
    return jsonify({"status": "success", "phone": otp.mask_phone(phone)})


@phone_bp.route("/me", methods=["DELETE"])
@check_session_validity
def remove_phone():
    user = _signed_in_user()
    if not user:
        return _error("Not authenticated", 401)
    store.clear_phone(user)
    return jsonify({"status": "success"})
