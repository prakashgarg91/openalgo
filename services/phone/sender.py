"""Delivering a one-time code. The provider is chosen by ``PHONE_OTP_PROVIDER``.

Unset means phone sign-in is off. Nothing is ever sent to a provider that was not
asked for, and the code is never logged unless the trader chose ``console``.

- ``console``: writes the code to the server log. For trying the flow on your own computer.
- ``twilio``: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.
- ``msg91``: MSG91_AUTH_KEY, MSG91_TEMPLATE_ID (an OTP template approved for your sender id).

The two SMS providers are written against their public documentation and have not
been run against a live account here.
"""

from __future__ import annotations

import os

from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)

TIMEOUT = 10.0


class SenderError(Exception):
    """The code could not be delivered. The message is safe to show a trader."""


def provider() -> str | None:
    value = os.getenv("PHONE_OTP_PROVIDER", "").strip().lower()
    return value or None


def configured() -> bool:
    name = provider()
    if name == "console":
        return True
    if name == "twilio":
        return all(
            os.getenv(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER")
        )
    if name == "msg91":
        return all(os.getenv(k) for k in ("MSG91_AUTH_KEY", "MSG91_TEMPLATE_ID"))
    return False


def send(phone: str, code: str) -> None:
    name = provider()
    if not configured():
        raise SenderError("Phone sign-in is not set up on this server.")
    try:
        if name == "console":
            logger.warning("Phone sign-in code for %s is %s (console provider)", phone, code)
        elif name == "twilio":
            _twilio(phone, code)
        elif name == "msg91":
            _msg91(phone, code)
    except SenderError:
        raise
    except Exception:
        logger.exception("Could not deliver a phone sign-in code")
        raise SenderError(
            "The code could not be sent. Check your SMS provider settings and balance, then try again."
        ) from None


def _twilio(phone: str, code: str) -> None:
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    response = get_httpx_client().post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
        data={
            "To": phone,
            "From": os.environ["TWILIO_FROM_NUMBER"],
            "Body": f"Your OpenAlgo sign-in code is {code}. It works for 5 minutes.",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()


def _msg91(phone: str, code: str) -> None:
    response = get_httpx_client().post(
        "https://control.msg91.com/api/v5/otp",
        params={
            "template_id": os.environ["MSG91_TEMPLATE_ID"],
            "mobile": phone.lstrip("+"),
            "otp": code,
        },
        headers={"authkey": os.environ["MSG91_AUTH_KEY"]},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
