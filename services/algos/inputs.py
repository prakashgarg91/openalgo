"""Market input feed for the regime scorer.

The parsers are pure. ``collect`` is the one place that does I/O: broker quotes
for Nifty and India VIX, Nifty daily history, and a public feed for the US
indices, crude and the dollar index. Every source fails soft: a source that
cannot be reached leaves its inputs as ``None``, which the scorer reports as a
missing input and a lower confidence instead of reading it as zero.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from services.algos.context import MarketInputs
from utils.logging import get_logger

logger = get_logger(__name__)

_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_GLOBAL_SYMBOLS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "crude": "CL=F",
    "dxy": "DX-Y.NYB",
}
_FETCH_TIMEOUT = 6.0
_MA_WINDOW = 20


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
    for key, symbol in _GLOBAL_SYMBOLS.items():
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


def collect(api_key: str) -> MarketInputs:
    """Fetch every source once and assemble a snapshot."""
    return assemble_inputs(
        nifty=_quote(api_key, "NIFTY", "NSE_INDEX"),
        vix=_quote(api_key, "INDIAVIX", "NSE_INDEX"),
        closes=_daily_closes(api_key, "NIFTY", "NSE_INDEX"),
        globals_=_global_changes(),
    )
