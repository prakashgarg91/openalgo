"""Nightly capture of 1-minute candles for the active weekly Nifty option contracts.

Expired-contract history costs a paid plan and is gone from the free feed once a contract
expires. Capturing the day's candles every evening while the contracts are still live builds
the same history for nothing, and it is what a later holdout test on rules (see
docs/algos/option-capture.md) needs.

Read-only: it only reads candles and writes them to the Historify database. It places no order.
The functions that choose contracts and loop over them take their data source and store as
arguments, so they run without a broker or a database; ``default_*`` wire the real ones.
"""

import time
from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd

from utils.logging import get_logger

logger = get_logger(__name__)

UNDERLYING = "NIFTY"
EXCHANGE = "NFO"
INDEX_SYMBOL = "NIFTY"
INDEX_EXCHANGE = "NSE_INDEX"
INTERVAL = "1m"
STRIKE_STEP = 50
STRIKES_EACH_SIDE = 16  # about +/- 800 points, wide enough for a 400-point spread and its stop

HistoryFn = Callable[[str, str, str, str, str], pd.DataFrame]
StoreFn = Callable[[pd.DataFrame, str, str, str], int]


def parse_expiry(text: str) -> datetime | None:
    for fmt in ("%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def nearest_expiry(expiries: list[str], today: datetime) -> str | None:
    """The first expiry on or after today, or None when none is left."""
    dated = [(parse_expiry(e), e) for e in expiries]
    upcoming = sorted((d, e) for d, e in dated if d is not None and d.date() >= today.date())
    return upcoming[0][1] if upcoming else None


def select_contracts(rows: list[dict], spot: float, expiry: str) -> list[dict]:
    """Option rows of one expiry within STRIKES_EACH_SIDE strikes of the at-the-money strike.

    Each row needs symbol, expiry, strike and instrumenttype (CE or PE).
    """
    atm = round(spot / STRIKE_STEP) * STRIKE_STEP
    low = atm - STRIKES_EACH_SIDE * STRIKE_STEP
    high = atm + STRIKES_EACH_SIDE * STRIKE_STEP
    return [
        r
        for r in rows
        if r.get("expiry") == expiry
        and r.get("instrumenttype") in ("CE", "PE")
        and r.get("strike") is not None
        and low <= float(r["strike"]) <= high
    ]


def capture(
    contracts: list[dict],
    day: str,
    history: HistoryFn,
    store: StoreFn,
) -> dict:
    """Fetch and store one day of 1-minute candles per contract.

    A contract that fails is counted and skipped; one bad contract never stops the night.
    """
    stored = candles = empty = failed = 0
    for row in contracts:
        symbol = row["symbol"]
        try:
            frame = history(symbol, EXCHANGE, INTERVAL, day, day)
            if frame is None or frame.empty:
                empty += 1
                continue
            candles += store(frame, symbol, EXCHANGE, INTERVAL)
            stored += 1
        except Exception:
            failed += 1
            logger.exception("Could not capture candles for %s", symbol)
    return {
        "contracts": len(contracts),
        "stored": stored,
        "candles": candles,
        "no_data": empty,
        "failed": failed,
    }


MAX_REQUESTS_PER_SECOND = 3  # the analytics token is shared with another app's market-data readers
RATE_LIMIT_PAUSE_SECONDS = 60


def paced(
    history: HistoryFn,
    per_second: float = MAX_REQUESTS_PER_SECOND,
    pause: float = RATE_LIMIT_PAUSE_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> HistoryFn:
    """Wrap a history source so it never exceeds ``per_second`` requests.

    A rate-limit reply (the text "429" in the error) waits ``pause`` seconds and tries once more.
    Any other error is raised unchanged for the caller to count.
    """
    gap = 1.0 / per_second
    last = [float("-inf")]

    def wait() -> None:
        ahead = last[0] + gap - clock()
        if ahead > 0:
            sleep(ahead)
        last[0] = clock()

    def call(*args: str) -> pd.DataFrame:
        wait()
        try:
            return history(*args)
        except Exception as exc:
            if "429" not in str(exc):
                raise
            logger.warning("Upstox rate limit reached; waiting %s seconds", pause)
            sleep(pause)
            wait()
            return history(*args)

    return call


VIX_SYMBOL = "INDIAVIX"
CONTEXT_DAYS_INDEX = 7
CONTEXT_DAYS_VIX = 45


def capture_context(day: str, history: HistoryFn, store: StoreFn) -> dict:
    """Save the Nifty index minutes and India VIX days that the forward shadow test reads.

    The index minutes cover the last week so the previous session's close is always there, and
    India VIX covers about six weeks of daily closes. Each source is saved on its own: one that
    fails is counted and logged, and the other is still saved.
    """
    end = datetime.strptime(day, "%Y-%m-%d")
    result = {"index_candles": 0, "vix_days": 0, "failed": 0}
    sources = (
        ("index_candles", INDEX_SYMBOL, INTERVAL, CONTEXT_DAYS_INDEX),
        ("vix_days", VIX_SYMBOL, "D", CONTEXT_DAYS_VIX),
    )
    for key, symbol, interval, back in sources:
        start = (end - timedelta(days=back)).strftime("%Y-%m-%d")
        try:
            frame = history(symbol, INDEX_EXCHANGE, interval, start, day)
            if frame is not None and not frame.empty:
                result[key] = store(frame, symbol, INDEX_EXCHANGE, interval)
        except Exception:
            result["failed"] += 1
            logger.exception("Could not capture %s", symbol)
    return result


def default_history(token: str) -> HistoryFn:
    from broker.upstox.api.data import BrokerData

    return paced(BrokerData(token).get_history)


def default_store() -> StoreFn:
    from database.historify_db import init_database, upsert_market_data

    init_database()
    return upsert_market_data


def option_rows(expiry: str) -> list[dict]:
    """Nifty option rows of one expiry from the master contract table."""
    from database.symbol import SymToken, db_session

    try:
        found = (
            db_session.query(SymToken)
            .filter(
                SymToken.exchange == EXCHANGE,
                SymToken.name == UNDERLYING,
                SymToken.expiry == expiry,
                SymToken.instrumenttype.in_(["CE", "PE"]),
            )
            .all()
        )
        return [
            {
                "symbol": s.symbol,
                "expiry": s.expiry,
                "strike": s.strike,
                "instrumenttype": s.instrumenttype,
            }
            for s in found
        ]
    finally:
        db_session.remove()


def spot_from_index(history: HistoryFn, day: str) -> float | None:
    """The last 1-minute close of the Nifty index for the day, or None when there is none."""
    frame = history(INDEX_SYMBOL, INDEX_EXCHANGE, INTERVAL, day, day)
    if frame is None or frame.empty:
        return None
    return float(frame.sort_values("timestamp")["close"].iloc[-1])
