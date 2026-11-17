"""Coarse market condition labels for each trading day, known by 09:15.

Pure module: no database, no broker, no network, no clock, no logging, no file access. Every
input arrives as an argument and every label leaves as a return value.

A label is a "cell". There are three real cells, one per volatility band: "low", "mid" and
"high". The band comes from the previous session's India VIX close, moved up one step when the
previous session's range was wide. Every input must be a fact known before the session opens,
and label_day only ever sees the one day it is given.

Event days carry the single cell "event", which means forced no-trade. Days with a missing VIX
close carry "unlabelled". gap_size is kept as a helper but label_day does not use it.
"""

from __future__ import annotations

import math
from typing import Any, Final

VIX_LOW: Final[float] = 14.0
VIX_HIGH: Final[float] = 18.0
RANGE_SPLIT_PCT: Final[float] = 1.0  # a previous range at or above this counts as wide
GAP_LARGE_PCT: Final[float] = 0.5  # an absolute gap at or above this is large

EVENT_CELL: Final[str] = "event"
UNLABELLED_CELL: Final[str] = "unlabelled"

_BANDS: Final[tuple[str, ...]] = ("low", "mid", "high")


def _missing(value: float | None) -> bool:
    """None and NaN (what a data table gives for a gap in the series) both mean 'not known'."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def volatility_band(vix_prev: float | None, range_prev_pct: float | None) -> str | None:
    """Volatility band from the previous session's VIX close, moved up one step for a wide range.

    None when the VIX close is missing, so the day stays unlabelled. A previous range at or above
    RANGE_SPLIT_PCT moves the band one step up; a band already at 'high' stays 'high'.
    """
    if _missing(vix_prev):
        return None
    if vix_prev < VIX_LOW:
        band = "low"
    elif vix_prev >= VIX_HIGH:
        band = "high"
    else:
        band = "mid"
    if not _missing(range_prev_pct) and range_prev_pct >= RANGE_SPLIT_PCT:
        band = _BANDS[min(_BANDS.index(band) + 1, len(_BANDS) - 1)]
    return band


def gap_size(gap_pct: float | None) -> str | None:
    """'large' when the absolute gap is at least GAP_LARGE_PCT, otherwise 'small'.

    The sign does not matter. None when the gap is missing. Not used by label_day.
    """
    if _missing(gap_pct):
        return None
    return "large" if abs(gap_pct) >= GAP_LARGE_PCT else "small"


def label_day(features: dict[str, Any]) -> str:
    """Cell for one trading day, built only from that day's own dict.

    Event days return "event" before anything else is checked. Otherwise the cell is the
    volatility band, and a missing VIX close returns "unlabelled".
    """
    if features.get("is_event"):
        return EVENT_CELL
    band = volatility_band(features.get("vix_prev"), features.get("range_prev_pct"))
    if band is None:
        return UNLABELLED_CELL
    return band


def all_cells() -> list[str]:
    """Every cell label that label_day can return, sorted. Five in total: three bands and two
    special cells."""
    return sorted([*_BANDS, EVENT_CELL, UNLABELLED_CELL])
