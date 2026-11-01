"""Replay the four registered alternative structures (docs/algos/structures-registration.md).

S1 uses the forward shadow machine with a 250-point spread, no stop and no reversal; S2 to S4 are
the weekly structures of services/algos/condor.py. Selection runs on the first 342 sessions and is
written to a file before the last 171 are replayed. Every result is reported under the earlier
cost model and the retail-realistic scenario. Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/structures_study.py <data_repo>
"""

import copy
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.algo_backtest import regime_spread_study as rs  # noqa: E402
from services.algos import condor  # noqa: E402
from services.algos import forward_shadow as fs  # noqa: E402
from services.algos.costs import realistic_cost  # noqa: E402

N_STRUCTURES = 4
BOOT_LEVEL = fs.BOOTSTRAP_LEVEL / N_STRUCTURES
MIN_SELECT_TRADES = 40
MIN_HELD_TRADES = 20
S1_RULES = fs.replace_rules(width=250, stop_pts=None, reverse=False)


def run_structure(name, bars, index, vix, period_days):
    allowed = set(period_days)
    if name == "S1":
        gated = fs.simulate_rule  # the registered machine, side C (always sell calls)
        from services.algos import regime_gate as rg

        return gated(
            "C", rg.GatedBars(bars, allowed), index, vix, rules=S1_RULES, last_bar=condor.LAST_BAR
        )
    return condor.simulate_weekly(condor.SPECS[name], bars, index, vix, allowed)


def legs_of(trade: dict) -> list[dict]:
    if "legs" in trade:
        return trade["legs"]
    return [
        {
            "entry_s": trade["entry_s"], "entry_l": trade["entry_l"],
            "exit_s": trade["exit_s"], "exit_l": trade["exit_l"],
        }
    ]  # fmt: skip


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
        )
        for g in legs_of(trade)
    )


def falling_flags(index: pd.DataFrame) -> pd.Series:
    """True for sessions that follow a negative Nifty return over the previous 20 sessions."""
    close = index["close"].groupby(index.index.normalize()).last()
    trailing = close.shift(1) / close.shift(21) - 1
    return trailing < 0


def metrics(result: fs.ShadowResult, all_days: list, period: list, falling: pd.Series) -> dict:
    trades = result.trades
    episodes = fs.episodes_closed(result) if result.rule == "S1" else len(trades)
    real = copy.copy(result)
    real.trades, costs = [], []
    for t in trades:
        c = real_cost(t)
        costs.append(c)
        real.trades.append({**t, "cost": c, "net": t["pts"] * t["lot"] - c})
    last = max([t["exit"].normalize() for t in trades] + [period[-1]]) if trades else period[-1]
    eq_days = [d for d in all_days if period[0] <= d <= last]
    paths = fs.equity_paths(real, eq_days)
    daily = fs.daily_pnl(paths["eod"])
    cons_net = float(sum(t["net"] for t in trades))
    real_net = float(sum(t["net"] for t in real.trades))
    split = {"falling": 0.0, "not_falling": 0.0}
    for t in real.trades:
        split["falling" if bool(falling.get(t["entry"].normalize(), False)) else "not_falling"] += (
            t["net"]
        )
    return {
        "trades": episodes,
        "pre_cost_net": round(float(sum(t["pts"] * t["lot"] for t in trades))),
        "conservative_net": round(cons_net),
        "realistic_net": round(real_net),
        "realistic_net_2x": round(real_net - sum(costs)),
        "drawdown": round(fs.max_drawdown(paths)),
        "worst_day": round(fs.worst_day(paths)),
        "realistic_net_by_market": {k: round(v) for k, v in split.items()},
        "boot_lower": float(fs.block_bootstrap_lower(daily.to_numpy(), BOOT_LEVEL)),
        "skipped": dict(result.skipped),
        "still_open": len(result.open_positions),
    }


def main() -> int:
    repo = Path(sys.argv[1])
    out = repo / "research" / "structures"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        bars, _ = rs.load_bars(repo, Path(scratch))
        index, vix = rs.load_index(repo), rs.load_vix(repo)
        days = bars.days()
        cut = days[2 * len(days) // 3 - 1]
        sel_days = [d for d in days if d <= cut]
        held_days = [d for d in days if d > cut]
        falling = falling_flags(index)
        names = ["S1", "S2", "S3", "S4"]
        selection = {
            n: metrics(run_structure(n, bars, index, vix, sel_days), days, sel_days, falling)
            for n in names
        }
        candidates = [
            n
            for n, m in selection.items()
            if m["trades"] >= MIN_SELECT_TRADES and m["realistic_net_2x"] > 0
        ]
        (out / "selection.json").write_text(
            json.dumps({"cells": selection, "candidates": candidates}, indent=2), encoding="utf-8"
        )
        print(f"selection period ({len(sel_days)} sessions): candidates {candidates or 'none'}")
        for n, m in selection.items():
            print(
                f"  {n}: trades {m['trades']}, before costs {m['pre_cost_net']:,}, earlier model {m['conservative_net']:,}, "
                f"realistic {m['realistic_net']:,}, at twice {m['realistic_net_2x']:,}, drawdown {m['drawdown']:,}"
            )
        print("Selection written; the held-out third is replayed only now.")
        held = {
            n: metrics(run_structure(n, bars, index, vix, held_days), days, held_days, falling)
            for n in names
        }
    report = {"held_out": held, "candidates": candidates, "passed": []}
    for n in candidates:
        m = held[n]
        gates = {
            "trades": m["trades"] >= MIN_HELD_TRADES,
            "net": m["realistic_net"] > 0,
            "net_2x": m["realistic_net_2x"] > 0,
            "drawdown": m["drawdown"] <= fs.MAX_DRAWDOWN,
            "worst_day": m["worst_day"] >= -fs.DAILY_CAP,
            "bootstrap": m["boot_lower"] > 0,
        }
        m["gates"] = gates
        if all(gates.values()):
            report["passed"].append(n)
    (out / "held_out.json").write_text(
        json.dumps(report, indent=2, default=float), encoding="utf-8"
    )
    print(f"held-out third ({len(held_days)} sessions): passed {report['passed'] or 'none'}")
    for n, m in held.items():
        print(
            f"  {n}: trades {m['trades']}, before costs {m['pre_cost_net']:,}, earlier model {m['conservative_net']:,}, "
            f"realistic {m['realistic_net']:,}, at twice {m['realistic_net_2x']:,}, drawdown {m['drawdown']:,}, "
            f"worst day {m['worst_day']:,}"
        )
    print(json.dumps({n: held[n]["realistic_net_by_market"] for n in held}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
