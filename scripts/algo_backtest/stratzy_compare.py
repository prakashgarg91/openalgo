"""Does a published overnight credit spread's recipe beat ours, on real option prices?

Another provider describes its Nifty overnight credit spread as: exit at 3 PM the
next day, best when India VIX is 13 to 20, started from Rs 1 lakh. Ours exits at
the next open and has no VIX band. This replays both recipes on actual NSE option
prices and prints every cell, with the result split into three periods.

Pre-registered grid (fixed before any result was read): shape (OTM1/OTM4,
OTM2/OTM5) x side rule (follow the regime lean, bull put only) x exit (next open,
next close as a stand-in for 3 PM) x VIX band (none, 13 to 20). Regime labels
calm and trending, confidence 0.5, expiry eve skipped, one lot, itemised costs.
Stops and targets cannot be replayed on daily prices and are left out for both.

Usage:
    uv run python scripts/algo_backtest/stratzy_compare.py <history_dir> <nse_days_dir>
"""

import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_data import load_dir  # noqa: E402

from services.algos import lab  # noqa: E402
from services.algos.templates import Plan, spread_config  # noqa: E402

history = load_dir(sys.argv[1])
real = lab.load_real_prices(Path(sys.argv[2]))
first, last = min(real._days), max(real._days)
vix_close = history.frames["vix"]["Close"]

SHAPES = [(1, 4), (2, 5)]
SIDES = ["follow-lean", "bull-put-only"]
EXITS = ["open", "close"]
BANDS = [None, (13.0, 20.0)]
# Three consecutive periods: choose / validate / untouched test.
SEGMENTS = [
    ("2022-01-01", "2023-06-30"),
    ("2023-07-01", "2024-12-31"),
    ("2025-01-01", "2026-12-31"),
]


def make_plan_fn(short, long, side_rule, band):
    def skip(reason):
        return Plan("zen", "skip", reason, None, 0, None, None)

    def plan_fn(regime, inputs, dte, extra):
        if regime.label not in ("calm", "trending") or regime.confidence < 0.5:
            return skip("regime")
        if dte <= 1:
            return skip("expiry eve")
        if band is not None:
            v = float(vix_close.loc[: extra["date"]].iloc[-1])
            if not band[0] <= v <= band[1]:
                return skip("vix band")
        side = (
            "bear_call" if (side_rule == "follow-lean" and regime.bias == "bearish") else "bull_put"
        )
        if side_rule == "bull-put-only" and regime.bias != "bullish":
            return skip("not bullish")
        cfg = spread_config(
            "c", side, 1, "weekly", short_offset=f"OTM{short}", long_offset=f"OTM{long}"
        )
        return Plan("zen", "trade", "", cfg, 1, 0.0, side)

    return plan_fn


def row(m):
    if not m["trades"]:
        return "n=  0"
    return f"n={m['trades']:3d} win={m['win_rate']:4.1f}% total={m['total']:8.0f} maxDD={m['max_drawdown']:7.0f}"


print(f"Real prices {first.date()} to {last.date()}  ({len(real)} days)\n")
cells = []
for (short, long), side, ex, band in product(SHAPES, SIDES, EXITS, BANDS):
    fn = make_plan_fn(short, long, side, band)
    name = f"OTM{short}/OTM{long} {side:13s} exit-{ex:5s} vix {'13-20' if band else 'any  '}"
    full = lab.run_lab(
        history,
        "zen",
        model="conservative",
        start=first.strftime("%Y-%m-%d"),
        end=last.strftime("%Y-%m-%d"),
        real=real,
        plan_fn=fn,
        exit_field=ex,
    )
    segs = []
    for s, e in SEGMENTS:
        r = lab.run_lab(
            history,
            "zen",
            model="conservative",
            start=s,
            end=e,
            real=real,
            plan_fn=fn,
            exit_field=ex,
        )
        segs.append(r.metrics)
    cells.append((name, full.metrics, segs))
    print(f"{name}\n  all  {row(full.metrics)}")
    for (s, e), m in zip(SEGMENTS, segs, strict=True):
        print(f"  {s[:7]}..{e[:7]} {row(m)}")

lost = sum(1 for _, _, segs in cells if segs[2]["trades"] and segs[2]["total"] < 0)
print(f"\n{len(cells)} cells tried; {lost} lost money in the untouched last period.")
