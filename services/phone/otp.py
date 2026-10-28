"""One-time codes for phone sign-in. Pure apart from the clock and the store passed in.

Rules, each one closing a way a six-digit code gets guessed or farmed:

- a code lives five minutes and works once;
- five wrong guesses burn it, so six digits cannot be walked through;
- a new code cannot be asked for inside a minute, and a phone gets five codes an hour,
  so the SMS bill and the target's phone cannot be flooded;
- codes are stored as keyed hashes and compared in constant time;
- the caller learns nothing about which numbers are registered: ``issue`` always
  returns the same shape, and it is the caller that decides whether to send.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass

from utils import real_threading

CODE_DIGITS = 6
TTL_SECONDS = 300
MAX_ATTEMPTS = 5
RESEND_AFTER_SECONDS = 60
MAX_SENDS_PER_HOUR = 5
HOUR = 3600

_INDIAN_MOBILE = re.compile(r"^[6-9]\d{9}$")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalise_phone(raw: str | None) -> str | None:
    """Return ``+<digits>`` or None. A bare 10-digit Indian mobile gets +91."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-().]", "", str(raw))
    if cleaned.startswith("0091"):
        cleaned = "+" + cleaned[2:]
    if _INDIAN_MOBILE.match(cleaned):
        return "+91" + cleaned
    if cleaned.startswith("91") and _INDIAN_MOBILE.match(cleaned[2:]):
        return "+" + cleaned
    return cleaned if _E164.match(cleaned) else None


def mask_phone(phone: str) -> str:
    return phone[:3] + "*" * max(len(phone) - 5, 0) + phone[-2:]


@dataclass(frozen=True)
class Issued:
    code: str | None  # None when the request was throttled
    retry_after: int  # seconds until another code may be asked for; 0 if none


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str  # "ok" | "wrong" | "expired" | "locked" | "none"


class OtpBook:
    """In-memory book of live codes. One process, like the rest of the app's state."""

    def __init__(
        self,
        secret: str,
        store: MutableMapping,
        sends: MutableMapping,
        clock: Callable[[], float],
    ) -> None:
        self._secret = secret.encode()
        self._store = store
        self._sends = sends
        self._clock = clock
        self._lock = real_threading.RLock()

    def _digest(self, purpose: str, phone: str, code: str) -> str:
        msg = f"{purpose}|{phone}|{code}".encode()
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    def issue(self, purpose: str, phone: str) -> Issued:
        with self._lock:
            return self._issue(purpose, phone)

    def _issue(self, purpose: str, phone: str) -> Issued:
        now = self._clock()
        key = (purpose, phone)
        live = self._store.get(key)
        if live and now - live["sent_at"] < RESEND_AFTER_SECONDS:
            return Issued(None, int(RESEND_AFTER_SECONDS - (now - live["sent_at"])) + 1)
        recent = [t for t in self._sends.get(phone, []) if now - t < HOUR]
        if len(recent) >= MAX_SENDS_PER_HOUR:
            return Issued(None, int(HOUR - (now - recent[0])) + 1)
        code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
        self._store[key] = {
            "hash": self._digest(purpose, phone, code),
            "sent_at": now,
            "expires": now + TTL_SECONDS,
            "attempts": 0,
        }
        self._sends[phone] = [*recent, now]
        return Issued(code, 0)

    def verify(self, purpose: str, phone: str, code: str) -> Verdict:
        # Check, count and burn happen in one hold, or parallel guesses beat the cap.
        with self._lock:
            return self._verify(purpose, phone, code)

    def _verify(self, purpose: str, phone: str, code: str) -> Verdict:
        key = (purpose, phone)
        live = self._store.get(key)
        if not live:
            return Verdict(False, "none")
        if self._clock() > live["expires"]:
            self._store.pop(key, None)
            return Verdict(False, "expired")
        if live["attempts"] >= MAX_ATTEMPTS:
            self._store.pop(key, None)
            return Verdict(False, "locked")
        live["attempts"] += 1
        self._store[key] = live
        if hmac.compare_digest(live["hash"], self._digest(purpose, phone, str(code))):
            self._store.pop(key, None)
            return Verdict(True, "ok")
        if live["attempts"] >= MAX_ATTEMPTS:
            self._store.pop(key, None)
            return Verdict(False, "locked")
        return Verdict(False, "wrong")
