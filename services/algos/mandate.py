"""The account's own rules: how much money, and the most it may lose in one day.

A mandate of Rs 1,00,000 capital and Rs 20,000 daily loss turns into one number the sizing uses,
20 percent of capital, and into a check a replay can run: did any day lose more than the cap.
Pure apart from reading one setting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

MAX_PCT = 50.0  # a cap above half the capital is a typo, not a plan


@dataclass(frozen=True)
class Mandate:
    capital: float
    max_daily_loss: float

    @property
    def max_loss_pct(self) -> float:
        return min(MAX_PCT, 100.0 * self.max_daily_loss / self.capital)

    def lots(self, width_pts: float, lot_size: int) -> int:
        """Lots whose worst case fits the daily cap. A defined-risk spread loses at most its width."""
        return int(self.max_daily_loss // (width_pts * lot_size))


#: The mandate this work was asked to test.
ONE_LAKH = Mandate(capital=100_000.0, max_daily_loss=20_000.0)


def daily_cap_from_env() -> float | None:
    """``ALGO_MAX_DAILY_LOSS_INR``: the most all algos together may put at risk in a day."""
    raw = os.getenv("ALGO_MAX_DAILY_LOSS_INR", "").strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def effective_pct(capital: float, default_pct: float, explicit: float | None = None) -> float:
    """The loss limit, as a percent of capital, that sizing should use."""
    if explicit is not None:
        return explicit
    cap = daily_cap_from_env()
    if cap is None or capital <= 0:
        return default_pct
    return Mandate(capital, cap).max_loss_pct


def simulate(
    trades: list[dict[str, Any]], mandate: Mandate, lots: int = 1, *, lot_scale: float = 1.0
) -> dict[str, Any]:
    """Run per-lot trade results through the account: equity, worst day, drawdown, cap breaches.

    ``trades`` carry ``date`` and ``pnl`` per lot. ``lot_scale`` lets the caller rescale results
    measured with one lot size to another.
    """
    by_day: dict[str, float] = {}
    for trade in sorted(trades, key=lambda t: t["date"]):
        by_day[trade["date"]] = by_day.get(trade["date"], 0.0) + trade["pnl"] * lots * lot_scale
    equity, peak, worst_dd = mandate.capital, mandate.capital, 0.0
    low = mandate.capital
    breaches = []
    curve = []
    for day, pnl in by_day.items():
        equity += pnl
        peak = max(peak, equity)
        worst_dd = min(worst_dd, equity - peak)
        low = min(low, equity)
        if -pnl > mandate.max_daily_loss:
            breaches.append({"date": day, "loss": round(-pnl, 1)})
        curve.append([day, round(equity, 1)])
    days = list(by_day.values())
    return {
        "days_traded": len(days),
        "final_equity": round(equity, 1),
        "return_pct": round(100.0 * (equity - mandate.capital) / mandate.capital, 2),
        "worst_day": round(min(days), 1) if days else 0.0,
        "best_day": round(max(days), 1) if days else 0.0,
        "max_drawdown": round(worst_dd, 1),
        "max_drawdown_pct": round(100.0 * worst_dd / peak, 2) if peak else 0.0,
        "lowest_equity": round(low, 1),
        "ruined": low <= 0,
        "cap_breaches": breaches,
        "within_daily_cap": not breaches,
        "curve": curve,
    }
