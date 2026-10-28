"""Test Zen's reverse-engineered rules on 5-minute option bars.

Two parts, in this order:

1. Validation. Replay the 204 published entries (their time, side and strikes) under
   the stop, target and exit-time rules read from the table, and compare with what was
   published: entry price error, per-trade points, and how often the stop agrees. If the
   replay cannot reproduce the published result from the published entries, the exit
   rules are wrong or the fills are not what the bars show, and nothing after this is
   worth reading.
2. Rule grid. Only if part 1 holds: which side rule, with or without the stop and the
   reversal, with or without the VIX and gap filters, earns when the entry is chosen by
   the rule and not copied from the table. Pre-registered: 6 side rules x 3 exit styles x
   2 filters = 36 cells, shown in thirds of the available period so one lucky stretch is
   visible.

Needs the bars from fetch_upstox_expired.py. The published table is not stored in this
repository; pass its path (the same markdown table stratzy_zen_reverse.py reads).

Usage:
    uv run python scripts/algo_backtest/stratzy_zen_intraday.py <history_dir> <bars_dir> <table.md>
"""

import re
import sys
from dataclasses import replace
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import intraday  # noqa: E402
from services.algos.intraday import Rules  # noqa: E402

ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([\d-]+) ([\d:]+)\s*\|\s*([\d-]+) ([\d:]+)\s*\|\s*(PE|CE)\s*\|"
    r"\s*(\d+)/(\d+)\s*\|\s*([\d.]+)\s*\|\s*(-?[\d.]+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
    r"\s*(-?[\d,.]+)\s*\|\s*(-?[\d.]+)\s*\|\s*([TS])"
)


def parse_table(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if not m or int(m.group(1)) > 204:
            continue
        g = m.groups()
        ent = pd.Timestamp(f"{g[1]} {g[2]}")
        lot = intraday.lot_size_for(ent)
        pnl = float(g[12].replace(",", ""))
        rows.append(
            {
                "ent": ent,
                "kind": g[5],
                "sold": float(g[6]),
                "long": float(g[7]),
                "credit": float(g[8]),
                "debit": float(g[9]),
                "pub_pts": pnl / (int(g[10]) * lot),
                "cls": g[14],
            }
        )
    return rows


def thirds(trades: list[dict]) -> list[list[float]]:
    if not trades:
        return [[], [], []]
    nets = pd.Series(
        [t["net"] for t in trades], index=pd.DatetimeIndex([t["entry"] for t in trades])
    )
    edges = nets.index.min() + (nets.index.max() - nets.index.min()) * np.array([1 / 3, 2 / 3])
    return [
        nets[nets.index <= edges[0]].tolist(),
        nets[(nets.index > edges[0]) & (nets.index <= edges[1])].tolist(),
        nets[nets.index > edges[1]].tolist(),
    ]


def stats(values: list[float]) -> str:
    if not values:
        return "n=  0"
    cum = np.cumsum(values)
    dd = float(np.min(cum - np.maximum.accumulate(np.r_[0.0, cum])[1:]))
    return f"n={len(values):3d} win={np.mean(np.array(values) > 0):4.0%} total={sum(values):8.0f} maxDD={dd:8.0f}"


def validate(bars: intraday.OptionBars, rows: list[dict]) -> bool:
    print("1. Validation: the published entries, replayed under the exit rules\n")
    rules = replace(Rules(), reverse=False)
    out = intraday.replay_published(bars, rows, rules)
    if len(out) < 20:
        print(
            f"   Only {len(out)} of {len(rows)} published trades could be priced from the bars; too few to validate."
        )
        return False
    pub = {(r["ent"].floor("5min"), r["kind"], r["sold"]): r for r in rows}
    sim = pd.DataFrame(out)
    sim["pub_pts"] = [pub[(t["entry"], t["side"], t["sold"])]["pub_pts"] for t in out]
    sim["pub_stop"] = [pub[(t["entry"], t["side"], t["sold"])]["cls"] == "S" for t in out]
    err = (sim["credit"] - sim["published_credit"]).abs()
    print(f"   Priced {len(sim)} of {len(rows)} published trades")
    print(
        f"   Entry credit from the bars vs published: median error {err.median():.1f} points, within 5 points on {(err <= 5).mean():.0%}"
    )
    print(
        f"   Published: {sim['pub_pts'].sum():8.0f} points, {sim['pub_pts'].mean():6.1f} per trade, win {(sim['pub_pts'] > 0).mean():.0%}"
    )
    print(
        f"   Replay:    {sim['pts'].sum():8.0f} points, {sim['pts'].mean():6.1f} per trade, win {(sim['pts'] > 0).mean():.0%}"
    )
    corr = float(np.corrcoef(sim["pub_pts"], sim["pts"])[0, 1])
    print(f"   Correlation per trade: {corr:+.2f}")
    stopped = sim["reason"] == "stop"
    both = int((stopped & sim["pub_stop"]).sum())
    print(
        f"   Stops: published {int(sim['pub_stop'].sum())}, replay {int(stopped.sum())}, both {both}"
    )
    print(f"   Exit reasons in the replay: {sim['reason'].value_counts().to_dict()}")
    ok = corr >= 0.8 and abs(sim["pts"].sum() - sim["pub_pts"].sum()) <= 0.25 * abs(
        sim["pub_pts"].sum()
    )
    print(
        f"\n   The replay {'reproduces' if ok else 'does NOT reproduce'} the published result "
        "(correlation 0.8 or more and total within 25%).\n"
    )
    return ok


GRID_SIDES = ["put", "call", "vs_prev_close", "vs_morning", "lean", "flip"]
GRID_EXITS = {
    "stop+reverse": {"stop_pts": 43.8, "target_pts": 10.0, "reverse": True},
    "stop only": {"stop_pts": 43.8, "target_pts": 10.0, "reverse": False},
    "no stop": {"stop_pts": None, "target_pts": None, "reverse": False},
}
GRID_FILTERS = {
    "none": {"vix_ceiling": None, "gap_floor": None},
    "zen": {"vix_ceiling": 20.0, "gap_floor": -0.01},
}


def grid(bars: intraday.OptionBars, context: pd.DataFrame) -> None:
    print("2. Rule grid (36 cells, one lot, conservative costs; thirds of the period)\n")
    cells = []
    for side, (exit_name, ex), (filt_name, flt) in product(
        GRID_SIDES, GRID_EXITS.items(), GRID_FILTERS.items()
    ):
        rules = replace(Rules(side_rule=side), **ex, **flt)
        result = intraday.simulate(bars, context, rules)
        parts = thirds(result.trades)
        cells.append((side, exit_name, filt_name, [t["net"] for t in result.trades], parts))
        print(
            f"{side:13s} {exit_name:12s} filter-{filt_name:4s} {stats([t['net'] for t in result.trades])}"
        )
        print("    thirds: " + " | ".join(f"{sum(p):8.0f}" for p in parts))
    last = sum(1 for c in cells if c[4][2] and sum(c[4][2]) < 0)
    allpos = [c for c in cells if all(p and sum(p) > 0 for p in c[4])]
    print(f"\n{len(cells)} cells tried; {last} lost money in the last third.")
    print(f"Cells profitable in all three thirds: {len(allpos)}")
    for side, exit_name, filt_name, *_ in allpos:
        print(f"   {side} / {exit_name} / filter-{filt_name}")


def main() -> int:
    history, bars_dir, table = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    bars = intraday.OptionBars.load(bars_dir)
    days = bars.days()
    if not days:
        print("No bar files found. Run fetch_upstox_expired.py first.")
        return 1
    print(
        f"Bars: {len(bars.expiries())} expiries, {len(days)} sessions, {days[0].date()} to {days[-1].date()}\n"
    )
    nifty = pd.read_csv(history / "nsei.csv", parse_dates=["Date"]).set_index("Date")
    vix = pd.read_csv(history / "vix.csv", parse_dates=["Date"]).set_index("Date")["Close"]
    context = intraday.daily_context(nifty, vix)
    ok = validate(bars, parse_table(table))
    if not ok:
        print(
            "Stopping before the grid: a grid on exit rules that do not reproduce the published trades proves nothing."
        )
        return 2
    grid(bars, context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
