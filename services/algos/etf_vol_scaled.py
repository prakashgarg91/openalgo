"""Volatility-scaled equity and gold: the rule and its rejection screen (docs/algos/vol-scaled-etf-registration.md).

The rule, costs, benchmarks and gates were fixed in that registration before this code existed. This
module is pure: it reads daily closes and the India VIX and returns rows and numbers. It places no
order and touches no file or network.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from services.algos import eod_screen
from services.algos import etf_ledger as el

TARGET_VOL = 0.12
EQUITY_CAP = 0.80
BAND = 0.05
REALISED_DAYS = 20
WARMUP_SESSIONS = 300
BOOT_BLOCK = 3
BOOT_SEED = 20261102
TRIAL_NUMBER = 320
BOOT_LEVEL = 0.025 / TRIAL_NUMBER
LOSS_LIMIT = 20_000.0


def sigma(closes: pd.DataFrame, vix: pd.Series, i: int) -> float | None:
    """Forecast volatility on session ``i``: the mean of India VIX / 100 and the 20-session realised
    volatility of NIFTYBEES (annualised). None until both exist."""
    if i < REALISED_DAYS:
        return None
    level = vix.get(closes.index[i])
    if level is None or pd.isna(level) or float(level) <= 0:
        return None
    window = np.log(closes[el.NIFTY].iloc[i - REALISED_DAYS : i + 1].to_numpy(dtype=float))
    realised = float(np.std(np.diff(window), ddof=1) * np.sqrt(252))
    if not realised > 0:
        return None
    return (float(level) / 100.0 + realised) / 2.0


def equity_weight(forecast: float) -> float:
    """Target equity weight: TARGET_VOL / forecast, never above EQUITY_CAP."""
    return min(EQUITY_CAP, TARGET_VOL / forecast)


def make_targets_fn(vix: pd.Series):
    """The ledger's ``targets_fn``: decide only at a month-end (or on the first execution)."""
    aligned = vix.copy()
    aligned.index = pd.DatetimeIndex(aligned.index).normalize()

    def fn(closes: pd.DataFrame, i: int, book: el.Book, last: bool) -> dict[str, float] | None:
        if not (last or el.is_month_end(closes, i)):
            return None
        forecast = sigma(closes, aligned, i)
        if forecast is None:
            return None
        prices = {s: float(closes[s].iloc[i]) for s in (el.NIFTY, el.GOLD)}
        nav = book.value(prices)
        w = equity_weight(forecast)
        current = book.shares[el.NIFTY] * prices[el.NIFTY] / nav if nav > 0 else 0.0
        if not last and abs(current - w) <= BAND:
            return None
        return {el.NIFTY: w * nav, el.GOLD: (1.0 - w) / 2.0 * nav}

    return fn


def first_signal(closes: pd.DataFrame) -> str:
    """The first month-end after the warm-up: the registered first decision."""
    for i in range(WARMUP_SESSIONS, len(closes) - 1):
        if el.is_month_end(closes, i):
            return str(closes.index[i].date())
    raise ValueError("Not enough stored sessions for a first month-end.")


def _stats(rows: pd.DataFrame) -> dict[str, float]:
    trades = int(((rows["buy_notional"] + rows["sell_notional"]) > 0).sum())
    years = (rows["session"].iloc[-1] - rows["session"].iloc[0]).days / 365.25
    end = float(rows["nav"].iloc[-1])
    return {
        "net": end - el.CAPITAL,
        "end": end,
        "cagr": (end / el.CAPITAL) ** (1 / years) - 1 if years > 0 and end > 0 else float("nan"),
        "drawdown": float(rows["drawdown"].max()),
        "worst_day": float(rows["daily_pnl"].min()),
        "cost": float(rows["cumulative_cost"].iloc[-1]),
        "trading_sessions": trades,
    }


def monthly_excess(ledger: pd.DataFrame, matched: pd.DataFrame) -> pd.Series:
    """Rupee change of (ledger value minus matched-hold value) in each calendar month."""
    diff = pd.Series(
        ledger["nav"].to_numpy() - matched["nav"].to_numpy(),
        index=pd.DatetimeIndex(ledger["session"]),
    )
    month_end = diff.groupby([diff.index.year, diff.index.month]).last()
    return month_end.diff().fillna(month_end.iloc[0] - float(diff.iloc[0]))


def run_screen(closes: pd.DataFrame, vix: pd.Series) -> dict[str, Any]:
    """Run the registered configuration once on ``closes`` and return the gates and the numbers."""
    closes = el.validate(closes)
    start = first_signal(closes)
    fn = make_targets_fn(vix)
    ledgers, matched = {}, {}
    weights = None
    for variant, costs in (("base", el.COSTS_V1), ("double", el.DOUBLE_COSTS)):
        ledgers[variant] = el.run_ledger("vol_scaled", closes, start, costs, variant, targets_fn=fn)
        if weights is None:
            weights = el.average_weights(ledgers[variant].rows)
        matched[variant] = el.run_ledger(
            "vol_scaled", closes, start, costs, variant, matched=weights
        )
    base, base_m = ledgers["base"].rows, matched["base"].rows
    dbl, dbl_m = ledgers["double"].rows, matched["double"].rows
    s_base, s_dbl = _stats(base), _stats(dbl)
    m_base, m_dbl = _stats(base_m), _stats(dbl_m)
    excess_base = s_base["net"] - m_base["net"]
    excess_dbl = s_dbl["net"] - m_dbl["net"]
    diff = base["nav"].to_numpy() - base_m["nav"].to_numpy()
    half = len(diff) // 2
    first_half, second_half = float(diff[half] - diff[0]), float(diff[-1] - diff[half])
    monthly = monthly_excess(base, base_m)
    bound = eod_screen.bootstrap_lower(monthly.to_numpy(dtype=float), BOOT_LEVEL, BOOT_SEED)
    yearly = pd.Series(diff, index=pd.DatetimeIndex(base["session"]))
    yearly = (
        yearly.groupby(yearly.index.year)
        .last()
        .diff()
        .fillna(yearly.groupby(yearly.index.year).last().iloc[0] - float(diff[0]))
    )
    gates = {
        "net_positive_at_both_costs": s_base["net"] > 0 and s_dbl["net"] > 0,
        "drawdown_and_worst_day_within_limit": s_base["drawdown"] <= LOSS_LIMIT
        and s_base["worst_day"] >= -LOSS_LIMIT,
        "beats_matched_hold_at_both_costs": excess_base > 0 and excess_dbl > 0,
        "excess_positive_in_each_half": first_half > 0 and second_half > 0,
        "bootstrap_bound_above_zero": bool(bound > 0),
        "excess_positive_without_best_month": excess_base - float(monthly.max()) > 0,
    }
    benchmarks = {
        name: _stats(el.run_ledger(name, closes, start, el.COSTS_V1, "base").rows)
        for name in el.BENCHMARKS
    }
    return {
        "first_signal": start,
        "sessions": int(len(base)),
        "ledger": {"base": s_base, "double": s_dbl},
        "matched_hold": {"base": m_base, "double": m_dbl, "weights": weights},
        "excess": {"base": excess_base, "double": excess_dbl, "first_half": first_half, "second_half": second_half},
        "monthly_excess": {"months": int(len(monthly)), "mean": float(monthly.mean()), "best": float(monthly.max()), "boot_lower": float(bound), "level": BOOT_LEVEL},
        "years_beat_matched_hold": int((yearly > 0).sum()),
        "years_lost_to_matched_hold": int((yearly <= 0).sum()),
        "benchmarks": benchmarks,
        "gates": gates,
        "verdict": "eligible for a forward shadow ledger" if all(gates.values()) else "rejected",
    }  # fmt: skip
