"""Compare a published algo's daily results with a plain overnight spread on the same dates.

Reads a CSV of the published daily results (date, pnl_rupees), replays a bull put
and a bear call spread (OTM1/OTM4, one lot, every day, no filter) on real option
prices, and reports how often the signs agree under two date readings (the date
is the entry day, or the exit day), and how the published series relates to what
Nifty did.

Usage:
    uv run python scripts/algo_backtest/stratzy_pasted_days.py <history_dir> <nse_days_dir> <csv>
"""

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_data import load_dir  # noqa: E402

from services.algos import lab  # noqa: E402
from services.algos.templates import Plan, spread_config  # noqa: E402

history = load_dir(sys.argv[1])
real = lab.load_real_prices(Path(sys.argv[2]))
theirs = {r["date"]: float(r["pnl_rupees"]) for r in csv.DictReader(open(sys.argv[3]))}
start, end = min(theirs), max(theirs)
nifty = history.frames["nifty"]


def plan_fn_for(side):
    def plan_fn(regime, inputs, dte, extra):
        expiry = "next_week" if dte <= 1 else "weekly"
        cfg = spread_config("c", side, 1, expiry, short_offset="OTM1", long_offset="OTM4")
        return Plan("zen", "trade", "", cfg, 1, 0.0, side)

    return plan_fn


ours = {}
for side in ("bull_put", "bear_call"):
    for ex in ("open", "close"):
        r = lab.run_lab(
            history,
            "zen",
            model="conservative",
            start=start,
            end=end,
            gated=False,
            real=real,
            plan_fn=plan_fn_for(side),
            exit_field=ex,
        )
        ours[(side, ex)] = {t["date"]: t["pnl"] for t in r.trades}

days = [d.strftime("%Y-%m-%d") for d in nifty.index]
nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
prv = {days[i + 1]: days[i] for i in range(len(days) - 1)}
close = {d.strftime("%Y-%m-%d"): float(v) for d, v in nifty["Close"].items()}


def entry_for(d, reading):
    return d if reading == "entry" else prv.get(d)


print(
    f"Published days: {len(theirs)}; ours priced per variant: "
    f"{ {k: len(v) for k, v in ours.items()} }\n"
)
print("Sign agreement with the published days, and rupees per lot (ours) on those days")
for (side, ex), series in ours.items():
    for reading in ("entry", "exit"):
        pairs = [
            (theirs[d], series[e]) for d in theirs if (e := entry_for(d, reading)) and e in series
        ]
        if not pairs:
            continue
        a = np.array(pairs)
        agree = float(np.mean(np.sign(a[:, 0]) == np.sign(a[:, 1])))
        corr = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
        print(
            f"  {side:9s} exit-{ex:5s} date={reading:5s} n={len(a):2d} "
            f"agree={agree:5.1%} corr={corr:+.2f} our_total={a[:, 1].sum():8.0f}"
        )

print("\nNifty move on the published days (close to next close), sign vs published sign")
for reading in ("entry", "exit"):
    xs = []
    for d, p in theirs.items():
        e = entry_for(d, reading)
        if e and e in nxt:
            xs.append((p, close[nxt[e]] / close[e] - 1))
    a = np.array(xs)
    print(
        f"  date={reading:5s} n={len(a)} corr={np.corrcoef(a[:, 0], a[:, 1])[0, 1]:+.2f} "
        f"agree={np.mean(np.sign(a[:, 0]) == np.sign(a[:, 1])):5.1%}"
    )

first = min(theirs)
print(
    f"\nNifty close {first}: {close[first]:.0f}, {max(d for d in close if d <= end)}: "
    f"{close[max(d for d in close if d <= end)]:.0f}"
)
