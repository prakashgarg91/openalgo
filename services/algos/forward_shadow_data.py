"""Reads the stored candles the forward shadow test needs from the Historify database.

Kept apart from ``forward_shadow`` so that module stays free of any database. Read only.
"""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from services.algos.intraday import OptionBars

_NAME = re.compile(r"^NIFTY(\d{2}[A-Z]{3}\d{2})(\d+(?:\.\d+)?)(CE|PE)$")
_IST = "Asia/Kolkata"


def parse_contract(symbol: str) -> tuple[pd.Timestamp, str, float] | None:
    """(expiry, CE or PE, strike) from an OpenAlgo symbol such as NIFTY03NOV2625000CE."""
    found = _NAME.match(symbol)
    if not found:
        return None
    try:
        expiry = datetime.strptime(found.group(1), "%d%b%y")
    except ValueError:
        return None
    return pd.Timestamp(expiry), found.group(3), float(found.group(2))


def to_ist_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Historify rows (unix seconds) as candles indexed by India wall-clock time."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    stamps = pd.to_datetime(frame["timestamp"], unit="s", utc=True).dt.tz_convert(_IST)
    out = frame[["open", "high", "low", "close"]].copy()
    out.index = pd.DatetimeIndex(stamps.dt.tz_localize(None), name="timestamp")
    return out.sort_index()


def load() -> tuple[OptionBars, pd.DataFrame, pd.Series]:
    """Option candles, Nifty index minutes and the India VIX daily close, all from Historify."""
    from database import historify_db as db

    catalog = db.get_data_catalog()
    frames = {}
    for row in catalog:
        if row["exchange"] != "NFO" or row["interval"] != "1m":
            continue
        parsed = parse_contract(row["symbol"])
        if parsed is None:
            continue
        frame = to_ist_frame(db.get_ohlcv(row["symbol"], "NFO", "1m"))
        if not frame.empty:
            frames[parsed] = frame
    index = to_ist_frame(db.get_ohlcv("NIFTY", "NSE_INDEX", "1m"))
    vix_frame = to_ist_frame(db.get_ohlcv("INDIAVIX", "NSE_INDEX", "D"))
    vix = vix_frame["close"] if not vix_frame.empty else pd.Series(dtype=float)
    return OptionBars(frames), index, vix
