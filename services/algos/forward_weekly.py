"""Forward shadow ledgers of the weekly call spread (docs/algos/forward-s3n-registration.md).

L1 is the 100-point call spread under test (S3n); L2 is the same entry with the 250-point wing, kept
for reference. Both are replays of stored one-minute candles in sandbox mode: no order is placed.
Pure functions over bars and frames: no database, no network, no clock. The data is loaded by
``forward_shadow_data`` and the report is written by ``scripts/algo_backtest/run_forward_s3n.py``.
"""

from __future__ import annotations

import copy
from datetime import date
from datetime import time as dtime
from typing import Any

import numpy as np
import pandas as pd

from services.algos import condor
from services.algos import forward_shadow as fs
from services.algos.costs import realistic_cost
from services.algos.intraday import OptionBars

VERSION = "2026-11-01-v1"
LEDGERS = {"L1": 100, "L2": 250}  # ledger -> width of the wing in points
FIRST_EXPIRY = pd.Timestamp("2026-11-10")
LAST_CANDLE = dtime(15, 29)  # the last one-minute candle of a full session
END_TRADES = 26
END_DATE = pd.Timestamp("2027-05-31")
MIN_TRADES = 26
LOSS_LIMIT = 20_000.0  # drawdown, single-day loss and the stopping rule all use this
BOOT_BLOCK = 3
BOOT_DRAWS = 10_000
BOOT_SEED = 20261101
BOOT_LEVEL = 0.025


def run(bars: OptionBars, index_1m: pd.DataFrame, vix: pd.Series) -> dict[str, fs.ShadowResult]:
    """Both ledgers over every stored week from the first counted expiry."""
    days = set(bars.days())
    return {
        name: condor.simulate_weekly(
            condor.S3,
            bars,
            index_1m,
            vix,
            days,
            width=width,
            last_bar=LAST_CANDLE,
            require_entry_candle=True,
            first_expiry=FIRST_EXPIRY,
        )  # fmt: skip
        for name, width in LEDGERS.items()
    }


def real_cost(trade: dict) -> float:
    return sum(
        realistic_cost(
            trade["entry"],
            trade["exit"],
            g["entry_s"],
            g["entry_l"],
            g["exit_s"],
            g["exit_l"],
            trade["lot"],
        )  # fmt: skip
        for g in trade["legs"]
    )


def with_realistic_costs(result: fs.ShadowResult) -> fs.ShadowResult:
    """The same ledger with every trade's cost and net recomputed under the retail scenario."""
    out = copy.copy(result)
    out.trades = []
    for t in result.trades:
        c = real_cost(t)
        out.trades.append({**t, "cost": c, "net": t["pts"] * t["lot"] - c})
    return out


def bootstrap_lower(values: np.ndarray, level: float = BOOT_LEVEL) -> float:
    """Lower bound of the mean from a moving-block bootstrap over completed trades."""
    n = len(values)
    if n == 0:
        return float("nan")
    block = min(BOOT_BLOCK, n)
    rng = np.random.default_rng(BOOT_SEED)
    starts = rng.integers(0, n - block + 1, size=(BOOT_DRAWS, -(-n // block)))
    offsets = np.arange(block)
    picked = values[(starts[:, :, None] + offsets).reshape(BOOT_DRAWS, -1)[:, :n]]
    return float(np.quantile(picked.mean(axis=1), level))


def nifty_move(index_1m: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    close = index_1m["close"].groupby(index_1m.index.normalize()).last()
    close = close[(close.index >= start.normalize()) & (close.index <= end.normalize())]
    if len(close) < 2:
        return None
    return float(close.iloc[-1] / close.iloc[0] - 1)


def trailing_flags(index_1m: pd.DataFrame) -> pd.Series:
    """True for sessions that follow a negative Nifty return over the previous 20 sessions."""
    close = index_1m["close"].groupby(index_1m.index.normalize()).last()
    return (close.shift(1) / close.shift(21) - 1) < 0


def ledger_report(
    name: str,
    result: fs.ShadowResult,
    days: list[pd.Timestamp],
    falling: pd.Series,
) -> dict[str, Any]:
    real = with_realistic_costs(result)
    trades = real.trades
    nets = np.array([t["net"] for t in trades], dtype=float)
    costs = np.array([t["cost"] for t in trades], dtype=float)
    start = _first(real)
    in_play = [d for d in days if d >= start]
    paths = fs.equity_paths(real, in_play) if in_play else pd.DataFrame(columns=["eod", "low"])
    realised = float(nets.sum())
    split = {"falling": 0.0, "not_falling": 0.0}
    for t in trades:
        split["falling" if bool(falling.get(t["entry"].normalize(), False)) else "not_falling"] += (
            t["net"]
        )
    return {
        "ledger": name,
        "width": LEDGERS[name],
        "completed": len(trades),
        "still_open": len(real.open_positions),
        "pre_cost_net": round(float(sum(t["pts"] * t["lot"] for t in trades))),
        "earlier_model_net": round(float(sum(t["net"] for t in result.trades))),
        "realistic_net": round(realised),
        "realistic_net_2x": round(realised - float(costs.sum())),
        "best_trade_removed": round(realised - float(nets.max())) if len(nets) else None,
        "drawdown": round(fs.max_drawdown(paths)) if len(paths) else 0,
        "worst_day": round(fs.worst_day(paths)) if len(paths) else 0,
        "lowest_equity": round(float(paths["low"].min())) if len(paths) else 0,
        "boot_lower_mean": None if not len(nets) else round(bootstrap_lower(nets), 1),
        "net_by_trailing_market": {k: round(v) for k, v in split.items()},
        "trades": [_row(t) for t in trades],
        "open": [_row(t) for t in real.open_positions],
        "not_counted": [
            {"expiry": f"{w['expiry']:%Y-%m-%d}", "reason": w["reason"]}
            for w in result.weeks_skipped
        ],
    }


def _first(result: fs.ShadowResult) -> pd.Timestamp:
    entries = [t["entry"].normalize() for t in [*result.trades, *result.open_positions]]
    return min(entries) if entries else pd.Timestamp.max


def _row(t: dict) -> dict[str, Any]:
    out = {k: v for k, v in t.items() if k not in ("marks", "legs")}
    out["gap_days"] = (t["expiry"].normalize() - t["entry"].normalize()).days
    out["legs"] = [dict(g) for g in t["legs"]]
    return {
        k: (f"{v:%Y-%m-%d %H:%M}" if isinstance(v, pd.Timestamp) else v) for k, v in out.items()
    }


def decide(report: dict[str, Any], today: date | pd.Timestamp) -> dict[str, Any]:
    """Where L1 stands against the registered stop and pass rule.

    ``state`` is running, stopped (the loss limit was reached: a fail), or finished with a pass, a
    fail or inconclusive. Nothing is decided before the end except the stop.
    """
    n = report["completed"]
    if report["lowest_equity"] <= -LOSS_LIMIT or report["realistic_net"] <= -LOSS_LIMIT:
        return {
            "state": "stopped",
            "verdict": "fail",
            "why": "cumulative net reached the loss limit",
        }
    ended = n >= END_TRADES or pd.Timestamp(today) >= END_DATE
    gates = {
        "enough_trades": n >= MIN_TRADES,
        "net_positive": report["realistic_net"] > 0,
        "net_positive_at_2x_costs": report["realistic_net_2x"] > 0,
        "drawdown_within_limit": report["drawdown"] <= LOSS_LIMIT,
        "worst_day_within_limit": report["worst_day"] >= -LOSS_LIMIT,
        "bootstrap_bound_above_zero": report["boot_lower_mean"] is not None
        and report["boot_lower_mean"] > 0,
        "positive_without_best_trade": report["best_trade_removed"] is not None
        and report["best_trade_removed"] > 0,
    }
    if not ended:
        return {"state": "running", "verdict": None, "gates": gates, "trades_to_go": END_TRADES - n}
    if n < MIN_TRADES:
        return {"state": "finished", "verdict": "inconclusive", "gates": gates}
    return {
        "state": "finished",
        "verdict": "pass" if all(gates.values()) else "fail",
        "gates": gates,
    }


def build_report(
    results: dict[str, fs.ShadowResult],
    index_1m: pd.DataFrame,
    days: list[pd.Timestamp],
    today: date | pd.Timestamp,
) -> dict[str, Any]:
    falling = trailing_flags(index_1m)
    ledgers = {n: ledger_report(n, r, days, falling) for n, r in results.items()}
    ledgers["L1"]["status"] = decide(ledgers["L1"], today)
    started = [pd.Timestamp(t["entry"]) for r in results.values() for t in r.trades] or [
        FIRST_EXPIRY
    ]
    return {
        "version": VERSION,
        "sessions_stored": len(days),
        "first_counted_expiry": f"{FIRST_EXPIRY:%Y-%m-%d}",
        "ledgers": ledgers,
        "nifty_move_over_test": nifty_move(index_1m, min(started), days[-1]) if days else None,
    }
