"""Run the registered regime-gated spread test (docs/algos/regime-spread-registration.md).

Twelve cells (three side rules by four range gates) are replayed on the first two thirds of the
sessions; one is selected; only then is the last third replayed. ``--check`` only reports what data
is stored and replays nothing. Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/regime_spread_study.py <data_repo> [--check] [out_dir]
"""

import csv
import json
import sys
import tarfile
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import forward_shadow as fs  # noqa: E402
from services.algos import regime_gate as rg  # noqa: E402
from services.algos.intraday import OptionBars  # noqa: E402

MIN_SELECT_EPISODES = 60
MIN_HELD_EPISODES = 30
SIDES = ("A", "B", "C")


def read_daily(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index, utc=True)
    return frame.sort_index()


def complete_expiries(repo: Path) -> list[str]:
    manifest = repo / "MANIFEST.csv"
    with manifest.open(encoding="utf-8") as handle:
        return sorted(row["expiry"] for row in csv.DictReader(handle))


def load_bars(repo: Path, workdir: Path) -> tuple[OptionBars, list[str]]:
    expiries = complete_expiries(repo)
    for expiry in expiries:
        with tarfile.open(repo / "bars5m" / f"{expiry}.tar.gz") as tar:
            tar.extractall(workdir, filter="data")
    return OptionBars.load(workdir), expiries


def load_index(repo: Path) -> pd.DataFrame:
    frame = pd.read_csv(repo / "index" / "nifty_1m.csv", parse_dates=["timestamp"])
    return frame.set_index("timestamp").sort_index()[["open", "high", "low", "close"]]


def load_vix(repo: Path) -> pd.Series:
    bars = read_daily(repo / "context" / "daily" / "_INDIAVIX.csv")
    close = bars["close"].copy()
    close.index = pd.DatetimeIndex(
        close.index.tz_convert("Asia/Kolkata").tz_localize(None)
    ).normalize()
    return close


def cell_metrics(result: fs.ShadowResult, days: list[pd.Timestamp]) -> dict:
    paths = fs.equity_paths(result, days)
    net = float(sum(t["net"] for t in result.trades))
    cost = float(sum(t["cost"] for t in result.trades))
    return {
        "episodes": fs.episodes_closed(result),
        "trades": len(result.trades),
        "net": round(net, 2),
        "net_double_cost": round(net - cost, 2),
        "max_drawdown": round(fs.max_drawdown(paths), 2),
        "worst_day": round(fs.worst_day(paths), 2),
        "still_open": len(result.open_positions),
        "skipped": dict(result.skipped),
    }


def run_cell(side: str, gate: str, bars, index, vix, days, grp) -> fs.ShadowResult:
    allowed = {d for d in days if d in grp.index and rg.GATES[gate](int(grp[d]))}
    return fs.simulate_rule(side, rg.GatedBars(bars, allowed), index, vix)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    repo = Path(args[0])
    check = "--check" in sys.argv
    out_dir = Path(args[1]) if len(args) > 1 else repo / "research" / "regime_spread"
    out_dir.mkdir(parents=True, exist_ok=True)
    nifty = read_daily(repo / "context" / "daily" / "_NSEI.csv")
    vix_bars = read_daily(repo / "context" / "daily" / "_INDIAVIX.csv")
    frame = rg.range_frame(nifty, vix_bars)
    coef, cuts = rg.fit(frame)
    grp = rg.groups(frame, coef, cuts)
    with tempfile.TemporaryDirectory() as scratch:
        bars, expiries = load_bars(repo, Path(scratch))
        index, vix = load_index(repo), load_vix(repo)
        days = bars.days()
        cut = days[2 * len(days) // 3 - 1]
        sel_days = [d for d in days if d <= cut]
        held_days = [d for d in days if d > cut]
        print(
            f"{len(expiries)} expiries; {len(days)} sessions; selection {sel_days[0]:%Y-%m-%d} to "
            f"{sel_days[-1]:%Y-%m-%d} ({len(sel_days)}); held out {held_days[0]:%Y-%m-%d} to "
            f"{held_days[-1]:%Y-%m-%d} ({len(held_days)})"
        )
        mix = grp.reindex(days).value_counts().sort_index().to_dict()
        print(f"range groups over these sessions: {mix}")
        if check:
            return 0
        selection = {}
        for side in SIDES:
            for gate in rg.GATES:
                res = run_cell(side, gate, bars, index, vix, sel_days, grp)
                selection[f"{side}_{gate}"] = cell_metrics(res, sel_days)
        ok = {
            k: v
            for k, v in selection.items()
            if v["episodes"] >= MIN_SELECT_EPISODES and v["net_double_cost"] > 0
        }
        chosen = max(ok, key=lambda k: ok[k]["net"]) if ok else None
        (out_dir / "selection.json").write_text(
            json.dumps({"cells": selection, "selected": chosen}, indent=2), encoding="utf-8"
        )
        print(f"selection period: {len(ok)} of {len(selection)} cells qualify; selected: {chosen}")
        for k, v in selection.items():
            print(
                f"  {k}: episodes {v['episodes']}, net {v['net']:,.0f}, at 2x cost {v['net_double_cost']:,.0f}"
            )
        print("Selection written; the held-out third is replayed only now.")
        held = {}
        results = {}
        for side in SIDES:
            for gate in rg.GATES:
                res = run_cell(side, gate, bars, index, vix, held_days, grp)
                results[f"{side}_{gate}"] = res
                held[f"{side}_{gate}"] = cell_metrics(res, held_days)
        report = {
            "selected": chosen,
            "cells": held,
            "cells_lost_money": sum(v["net"] < 0 for v in held.values()),
        }
        if chosen:
            side, gate = chosen.split("_")
            daily = fs.daily_pnl(fs.equity_paths(results[chosen], held_days)["eod"])
            control = fs.daily_pnl(fs.equity_paths(results[f"{side}_none"], held_days)["eod"])
            m = held[chosen]
            gates = {
                "episodes": m["episodes"] >= MIN_HELD_EPISODES,
                "net": m["net"] > 0,
                "cost_stress": m["net_double_cost"] > 0,
                "drawdown": m["max_drawdown"] <= fs.MAX_DRAWDOWN,
                "daily_cap": m["worst_day"] >= -fs.DAILY_CAP,
                "mean_bound": fs.block_bootstrap_lower(daily.to_numpy()) > 0,
                "beats_ungated": gate != "none"
                and fs.block_bootstrap_lower((daily - control).to_numpy()) > 0,
            }
            report["gates"] = gates
            report["pass"] = all(gates.values())
        (out_dir / "held_out.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
