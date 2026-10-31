"""Retail-realistic round-trip cost of a two-leg credit spread (docs/algos/cost-scenario-registration.md).

Pure function over numbers: no database, no network, no file access, no clock. The conservative
model in ``lab.trade_cost`` stays as it is; this is a second scenario that is applied after the
fact to trades whose decisions did not depend on cost.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RealisticCosts:
    brokerage_per_order: float = 20.0
    stt_before: float = 0.001
    stt_after: float = 0.0015
    stt_change: pd.Timestamp = pd.Timestamp("2026-04-01")
    exchange_pct: float = 0.000345
    sebi_pct: float = 0.000001
    gst: float = 0.18
    stamp_pct: float = 0.00003
    slip_pts: float = 0.15


REALISTIC = RealisticCosts()


def realistic_cost(
    entry_day: pd.Timestamp,
    exit_day: pd.Timestamp,
    entry_short: float,
    entry_long: float,
    exit_short: float,
    exit_long: float,
    lot: int,
    c: RealisticCosts = REALISTIC,
) -> float:
    """Rupees for one spread, sold short leg and bought long leg at entry, reversed at exit."""
    turnover = (entry_short + entry_long + exit_short + exit_long) * lot
    stt = entry_short * lot * (
        c.stt_after if pd.Timestamp(entry_day) >= c.stt_change else c.stt_before
    ) + exit_long * lot * (c.stt_after if pd.Timestamp(exit_day) >= c.stt_change else c.stt_before)
    brokerage = 4 * c.brokerage_per_order
    exchange = turnover * c.exchange_pct
    sebi = turnover * c.sebi_pct
    gst = c.gst * (brokerage + exchange + sebi)
    stamp = (entry_long + exit_short) * lot * c.stamp_pct
    slippage = 4 * c.slip_pts * lot
    return brokerage + stt + exchange + sebi + gst + stamp + slippage
