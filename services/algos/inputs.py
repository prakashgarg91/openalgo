"""Market input feed for the regime scorer.

The parsers are pure. ``collect`` is the one place that does I/O: broker quotes
for Nifty and India VIX, Nifty daily history, and a public feed for the US
indices, crude and the dollar index. Every source fails soft: a source that
cannot be reached leaves its inputs as ``None``, which the scorer reports as a
missing input and a lower confidence instead of reading it as zero.
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import date, timedelta
from typing import Any

from services.algos.context import MarketInputs
from utils.logging import get_logger
from utils.thread_safe_cache import LockedTTLCache

logger = get_logger(__name__)

_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_GLOBAL_SYMBOLS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "crude": "CL=F",
    "dxy": "DX-Y.NYB",
}
_FETCH_TIMEOUT = 4.0
_GLOBALS_DEADLINE = 8.0
_MA_WINDOW = 20

# Several pages ask for the market reading at once (the regime, the chooser, the picker), and a reading costs
# two broker quotes, a month of daily history and four overseas fetches. The whole snapshot is kept for 30
# seconds, and the two slow sources, which change once a day, for ten minutes. One caller builds it at a time.
_SNAPSHOT_CACHE = LockedTTLCache(maxsize=8, ttl=30)
_SLOW_CACHE = LockedTTLCache(maxsize=16, ttl=600)
_collect_lock = threading.Lock()


def pct_change(now: float | None, previous: float | None) -> float | None:
    if now is None or not previous:
        return None
    return (float(now) / float(previous) - 1.0) * 100.0


def sma_distance_pct(closes: list[float] | None, window: int = _MA_WINDOW) -> float | None:
    """Distance of the latest close from its simple average, in percent."""
    if not closes or len(closes) < window:
        return None
    recent = [float(c) for c in closes[-window:]]
    average = sum(recent) / window
    return pct_change(recent[-1], average)


def yahoo_change_pct(payload: dict[str, Any]) -> float | None:
    """Last close against the one before it, from a Yahoo chart response."""
    try:
        result = (payload.get("chart") or {}).get("result")
        if not result:
            return None
        closes = result[0]["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    valid = [c for c in closes if c is not None]
    if len(valid) < 2:
        return None
    return pct_change(valid[-1], valid[-2])


def assemble_inputs(
    *,
    nifty: dict[str, Any] | None,
    vix: dict[str, Any] | None,
    closes: list[float] | None,
    globals_: dict[str, float | None],
) -> MarketInputs:
    nifty = nifty or {}
    vix = vix or {}
    vix_now = vix.get("ltp") or None
    return MarketInputs(
        gap_pct=pct_change(nifty.get("ltp"), nifty.get("prev_close")),
        sp500_pct=globals_.get("sp500"),
        nasdaq_pct=globals_.get("nasdaq"),
        crude_pct=globals_.get("crude"),
        dxy_pct=globals_.get("dxy"),
        vix=float(vix_now) if vix_now else None,
        vix_change_pct=pct_change(vix_now, vix.get("prev_close")),
        nifty_vs_ma20_pct=sma_distance_pct(closes),
        open_gap_pct=pct_change(nifty.get("open"), nifty.get("prev_close")),
    )


def _quote(api_key: str, symbol: str, exchange: str) -> dict[str, Any] | None:
    from services.quotes_service import get_quotes

    try:
        ok, response, _ = get_quotes(symbol=symbol, exchange=exchange, api_key=api_key)
    except Exception:
        logger.exception("Quote for %s:%s failed", exchange, symbol)
        return None
    if not ok:
        return None
    data = response.get("data")
    return data if isinstance(data, dict) else None


def _daily_closes(api_key: str, symbol: str, exchange: str) -> list[float] | None:
    from services.history_service import get_history

    end = date.today()
    start = end - timedelta(days=45)
    try:
        ok, response, _ = get_history(
            symbol=symbol,
            exchange=exchange,
            interval="D",
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            api_key=api_key,
        )
    except Exception:
        logger.exception("History for %s:%s failed", exchange, symbol)
        return None
    if not ok:
        return None
    rows = response.get("data") or []
    closes = [float(r["close"]) for r in rows if r.get("close") is not None]
    return closes or None


def _global_changes() -> dict[str, float | None]:
    from utils.httpx_client import get_httpx_client

    client = get_httpx_client()
    out: dict[str, float | None] = {}
    started = time.monotonic()
    for key, symbol in _GLOBAL_SYMBOLS.items():
        if time.monotonic() - started > _GLOBALS_DEADLINE:
            out[key] = None
            continue
        try:
            response = client.get(
                _YAHOO_URL.format(symbol=symbol),
                params={"range": "5d", "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=_FETCH_TIMEOUT,
            )
            out[key] = yahoo_change_pct(response.json()) if response.status_code == 200 else None
        except Exception:
            logger.warning("Global input %s could not be fetched", key)
            out[key] = None
    return out


def _slow(key: str, loader, worth_keeping) -> Any:
    """A source that changes once a day: kept ten minutes, but only when it actually answered."""
    return _SLOW_CACHE.get_or_load(key, loader, should_cache=worth_keeping)


def collect(api_key: str) -> MarketInputs:
    """Fetch every source and assemble a snapshot, reusing a recent one when several pages ask at once."""
    key = hashlib.sha256(api_key.encode()).hexdigest()
    cached = _SNAPSHOT_CACHE.get(key)
    if cached is not None:
        return cached
    with _collect_lock:
        cached = _SNAPSHOT_CACHE.get(key)
        if cached is not None:
            return cached
        snapshot = assemble_inputs(
            nifty=_quote(api_key, "NIFTY", "NSE_INDEX"),
            vix=_quote(api_key, "INDIAVIX", "NSE_INDEX"),
            closes=_slow(
                f"closes:{key}", lambda: _daily_closes(api_key, "NIFTY", "NSE_INDEX"), bool
            ),
            globals_=_slow(
                "globals",
                _global_changes,
                lambda v: any(x is not None for x in (v or {}).values()),
            )
            or {},
        )
        _SNAPSHOT_CACHE[key] = snapshot
        return snapshot
