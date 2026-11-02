"""Nifty lot size by contract expiry, from NSE circulars (docs/algos/eight-structure-screen-registration.md).

The lot is fixed by the contract's expiry date, not by the day a position is opened. Each start date
is the first expiry that carries the new lot; ``None`` is returned for an expiry before the first
documented one, so a study cannot silently use a guessed lot. Pure data and one function.
"""

from __future__ import annotations

import pandas as pd

# (first expiry with this lot, lot, source). Sources are the exchange's own circulars; the 2 Jan 2025
# start and the 26 Dec 2024 end of the 25-lot era also rest on the Upstox contract master, read on
# 2 November 2026 (docs/algos/lot-size-correction.md), because the October 2024 circular phases the
# change in by contract introduction date rather than by expiry.
NIFTY_LOTS: tuple[tuple[str, int, str], ...] = (
    (
        "2021-04-01",
        75,
        "NSE/FAOP/47854, 31 Mar 2021 (ref 28/2021): present lot 75 for existing contracts",
    ),
    (
        "2021-07-29",
        50,
        "NSE/FAOP/47854: July 2021 monthly and August 2021 weekly expiry onward revised to 50",
    ),
    (
        "2024-05-02",
        25,
        "NSE/FAOP/61415, 2 Apr 2024 (ref 37/2024): first weekly with 25 expires 2 May 2024",
    ),
    (
        "2025-01-02",
        75,
        "NSE/FAOP/64625, 18 Oct 2024 (ref 128/2024); first 2025 weekly per the Upstox contract master",
    ),
    (
        "2026-01-06",
        65,
        "NSE/FAOP/70616, 3 Oct 2025 (ref 176/2025): weekly and monthly keep 75 to 30 Dec 2025",
    ),
)
FIRST_DOCUMENTED = pd.Timestamp(NIFTY_LOTS[0][0])
# Not opened yet: the August 2015 revision (press reports 25 to 75, effective 28 August 2015). Until its
# circular is read and added above, no expiry before FIRST_DOCUMENTED has a lot and none is guessed.


def nifty_lot(expiry: pd.Timestamp | str) -> int | None:
    """Units per Nifty lot for a contract expiring on ``expiry``, or None if it is not documented."""
    when = pd.Timestamp(expiry).normalize()
    lot = None
    for start, size, _source in NIFTY_LOTS:
        if when >= pd.Timestamp(start):
            lot = size
    return lot if when >= FIRST_DOCUMENTED else None
