"""Reverse-engineer a published overnight credit spread from its own trade table.

Reads the markdown table of published trades (entry, exit, type, sold and long
strike, credit, exit debit, lots, P&L), matches every trade to real NSE option
prices, and reports:

  1. Structure: spread width, how far from spot the sold strike sits, lots.
  2. Prices: whether the published entry credit sits inside the exchange's real
     price range for that day.
  3. Timing: entry time, how long it waits when flat, which days it stays out
     (India VIX, opening gap, weekday), how it re-enters after a stop.
  4. Stop and target distances, and how the side (put or call) relates to the
     market before and after entry.
  5. Fidelity: what the same published trades earn when priced only from daily
     real prices (the open of the entry day to the close of the exit day), next
     to what was published, to show how much of the result depends on intraday
     management a daily replay cannot see.

The table itself is not stored in this repository; pass its path.

Usage:
    uv run python scripts/algo_backtest/stratzy_zen_reverse.py <history_dir> <nse_days_dir> <table.md>
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import lab  # noqa: E402

hist_dir, real_dir, table = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
real = lab.load_real_prices(real_dir)
nifty = pd.read_csv(hist_dir / "nsei.csv", parse_dates=["Date"]).set_index("Date")
vix = pd.read_csv(hist_dir / "vix.csv", parse_dates=["Date"]).set_index("Date")["Close"]
close, open_ = nifty["Close"], nifty["Open"]

ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([\d-]+) ([\d:]+)\s*\|\s*([\d-]+) ([\d:]+)\s*\|\s*(PE|CE)\s*\|"
    r"\s*(\d+)/(\d+)\s*\|\s*([\d.]+)\s*\|\s*(-?[\d.]+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
    r"\s*(-?[\d,.]+)\s*\|\s*(-?[\d.]+)\s*\|\s*([TS])"
)
rows = []
for line in table.read_text(encoding="utf-8").splitlines():
    m = ROW.match(line)
    if not m or int(m.group(1)) > 204:
        continue
    g = m.groups()
    ent = pd.Timestamp(f"{g[1]} {g[2]}")
    ex = pd.Timestamp(f"{ent.year}-{g[3]} {g[4]}")
    if ex < ent:
        ex = pd.Timestamp(f"{ent.year + 1}-{g[3]} {g[4]}")
    rows.append(
        {
            "n": int(g[0]),
            "ent": ent,
            "ex": ex,
            "kind": g[5],
            "sold": float(g[6]),
            "long": float(g[7]),
            "credit": float(g[8]),
            "debit": float(g[9]),
            "lots": int(g[10]),
            "pnl": float(g[12].replace(",", "")),
            "cls": g[14],
        }
    )
d = pd.DataFrame(rows)
d["day"] = d["ent"].dt.normalize()
d["exit_day"] = d["ex"].dt.normalize()
d["width"] = (d["sold"] - d["long"]).abs()
d["put"] = d["kind"] == "PE"
print(f"{len(d)} published trades, {d['day'].min().date()} to {d['day'].max().date()}")
print(
    "1. Width:",
    d["width"].value_counts().to_dict(),
    " lots:",
    d["lots"].value_counts().sort_index().to_dict(),
)


def band(day, expiry, sold, long_, kind):
    """Lowest and highest of the spread's open-based and close-based value, or None."""
    vals = []
    for field in ("open", "close"):
        a = real._price(day, expiry, sold, kind, field)
        b = real._price(day, expiry, long_, kind, field)
        if a is not None and b is not None:
            vals.append(a - b)
    return (min(vals), max(vals)) if vals else None


# Match each trade to the weekly expiry whose real prices fit its credit best.
exp_of, err_of = {}, {}
for r in d.itertuples():
    best = None
    for e in real.expiries(r.day):
        if (e - r.day).days > 8:
            continue
        b = band(r.day, e, r.sold, r.long, r.kind)
        if b is None:
            continue
        err = max(b[0] - r.credit, r.credit - b[1], 0.0)
        key = (err, abs(r.credit - (b[0] + b[1]) / 2))
        if best is None or key < best[0]:
            best = (key, e)
    if best:
        exp_of[r.n], err_of[r.n] = best[1], best[0][0]
d["expiry"] = d["n"].map(exp_of)
d["err"] = d["n"].map(err_of)
d["dte"] = (d["expiry"] - d["day"]).dt.days
m = d.dropna(subset=["expiry"]).copy()
sign = np.where(m["put"], 1, -1)  # positive = sold strike is below spot (out of the money)
m["off_open"] = sign * (open_.reindex(m["day"]).to_numpy() - m["sold"])
print(f"\n2. Matched to a weekly expiry (8 days or less): {len(m)} of {len(d)}")
print(
    f"   Published credit within 10 points of the real open-close range: {(m['err'] <= 10).mean():.0%}"
)
print(f"   within 25 points: {(m['err'] <= 25).mean():.0%}")
print("   Days to expiry at entry:", m["dte"].value_counts().sort_index().to_dict())
q = m["off_open"].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).round(0).tolist()
print(f"   Sold strike vs that day's open, points (+ is out of the money): p10/25/50/75/90 = {q}")
for k in ("PE", "CE"):
    print(f"   {k}: median {m[m['kind'] == k]['off_open'].median():+.0f}")

print("\n3. Timing")
print("   Entry hour:", d["ent"].dt.hour.value_counts().sort_index().to_dict())
print("   Exit time:", d["ex"].dt.strftime("%H:%M").value_counts().head(6).to_dict())
days = [x for x in nifty.index if d["day"].min() <= x <= d["day"].max()]
flat_rows = []
for x in days:
    t1015 = x + pd.Timedelta(hours=10, minutes=15)
    held = ((d["ent"] < t1015) & (d["ex"] > t1015)).any()
    entered = ((d["day"] == x) & (d["ent"] <= x + pd.Timedelta(hours=11))).any()
    flat_rows.append(
        {
            "held": held,
            "entered": entered,
            "vix": float(vix.shift(1).get(x, np.nan)),
            "gap": float(open_[x] / close.shift(1)[x] - 1),
            "wd": x.dayofweek,
        }
    )
f = pd.DataFrame(flat_rows)
fl = f[~f["held"]]
print(
    f"   Sessions {len(f)}; flat at 10:15: {len(fl)}; entered by 11:00: {int(fl['entered'].sum())}"
)
print(
    "   Entered share of flat sessions by weekday (Mon=0):",
    fl.groupby("wd")["entered"].mean().round(2).to_dict(),
)
for lo, hi in [(0, 13), (13, 15), (15, 17), (17, 20), (20, 25), (25, 99)]:
    x = fl[(fl["vix"] >= lo) & (fl["vix"] < hi)]
    share = f"{x['entered'].mean():4.0%}" if len(x) else "  n/a"
    print(f"   prior-close India VIX {lo:2d}-{hi:2d}: flat sessions {len(x):3d}, entered {share}")
for lo, hi in [(-1, -0.01), (-0.01, -0.005), (-0.005, 0.005), (0.005, 0.01), (0.01, 1)]:
    x = fl[(fl["gap"] >= lo) & (fl["gap"] < hi)]
    share = f"{x['entered'].mean():4.0%}" if len(x) else "  n/a"
    print(f"   opening gap {lo:+.3f} to {hi:+.3f}: flat sessions {len(x):3d}, entered {share}")
v = vix.shift(1).reindex(d["day"])
print(
    f"   India VIX on trade days: median {v.median():.1f}, 90th percentile {v.quantile(0.9):.1f}, max {v.max():.1f}"
)

print("\n4. Stop, target and side")
d["gap_min"] = (d["ent"] - d["ex"].shift(1)).dt.total_seconds() / 60
d["prev_cls"], d["prev_put"] = d["cls"].shift(1), d["put"].shift(1)
quick = d[(d["gap_min"] >= 0) & (d["gap_min"] <= 240)]
print(
    f"   Re-entry within 4 hours of the previous exit: {len(quick)} trades; "
    f"{(quick['prev_cls'] == 'S').mean():.0%} follow a stop; flips side {(quick['put'] != quick['prev_put']).mean():.0%}"
)
for cl in "TS":
    x = d[(d["gap_min"] > 240) & (d["prev_cls"] == cl)]
    print(
        f"   Next-session entry after a {cl} exit: {len(x)} trades, flips side {(x['put'] != x['prev_put']).mean():.0%}"
    )
lot = np.where(d["ent"] < pd.Timestamp("2026-01-01"), 75, 65)  # Nifty lot size changed
d["pts"] = d["pnl"] / (d["lots"] * lot)
loss = d[(d["cls"] == "S") & (d["pnl"] < 0)]
print(
    f"   Stop: spread value rises by {(-loss['pts']).median():.1f} points over the credit "
    f"(middle half {(-loss['pts']).quantile(0.25):.1f} to {(-loss['pts']).quantile(0.75):.1f}, {len(loss)} stops)"
)
win = d[d["pnl"] > 0]
print(
    f"   Winners: exit debit median {win['debit'].median():.1f} points; {int((d['debit'] <= 12).sum())} trades closed at 12 or less"
)
up = close.reindex(d["day"]).to_numpy() > open_.reindex(d["day"]).to_numpy()
print(
    f"   Put share when the entry day closes above its open {d['put'][up].mean():.0%} (n={up.sum()}), "
    f"below {d['put'][~up].mean():.0%} (n={(~up).sum()})"
)
gap = (open_ / close.shift(1)).reindex(d["day"]).to_numpy() - 1
print(
    f"   Put share after an opening gap up {d['put'][gap > 0].mean():.0%}, gap down {d['put'][gap <= 0].mean():.0%}"
)
sma = (close.shift(1) / close.rolling(20).mean().shift(1)).reindex(d["day"]).to_numpy() - 1
print(
    f"   Put share with prior close above its 20-day average {d['put'][sma > 0].mean():.0%}, below {d['put'][sma <= 0].mean():.0%}"
)


def value(day, expiry, sold, long_, kind, field):
    """Spread value from real prints; intrinsic after expiry; None when a live contract has no print."""
    a = real._price(day, expiry, sold, kind, field)
    b = real._price(day, expiry, long_, kind, field)
    if a is not None and b is not None:
        return a - b
    if pd.Timestamp(day) >= pd.Timestamp(expiry):
        s = float(close.get(min(pd.Timestamp(day), pd.Timestamp(expiry)), np.nan))
        if np.isnan(s):
            return None
        intr = (lambda k: max(0.0, k - s)) if kind == "PE" else (lambda k: max(0.0, s - k))
        return intr(sold) - intr(long_)
    return None


print("\n5. Same published trades, entered at the published credit, exited by daily rules")
print("   Entry is the published fill, so the side and strike choice cannot see the future;")
print("   only the stop, the target and the 15:00 timing are replaced by a plain close.")
sessions = list(nifty.index)
nxt_day = {sessions[i]: sessions[i + 1] for i in range(len(sessions) - 1)}
proxy = []
for r in d.loc[m.index].itertuples():
    same = value(r.day, r.expiry, r.sold, r.long, r.kind, "close")
    nd = nxt_day.get(r.day)
    nxt = value(nd, r.expiry, r.sold, r.long, r.kind, "close") if nd is not None else None
    if same is None or nxt is None:
        continue
    cost = lab.trade_cost(lab.CONSERVATIVE, [r.credit], [nxt], [True]) / lab.LOT_SIZE
    proxy.append(
        {
            "pub": r.pts,
            "same": r.credit - same,
            "nxt": r.credit - nxt,
            "nxt_net": r.credit - nxt - cost,
            "ent": r.ent,
        }
    )
p = pd.DataFrame(proxy)


def line(label, col):
    s = p[col]
    return (
        f"   {label:36s} {s.sum():7.0f} points, {s.mean():6.1f} per trade, win {(s > 0).mean():.0%}"
    )


print(f"   Priced {len(p)} of {len(m)} trades")
print(line("Published", "pub"))
print(line("Hold to the next session's close", "nxt"))
print(line("  after conservative costs", "nxt_net"))
print(line("Close the same day instead", "same"))
print(f"   Correlation with published (next close): {np.corrcoef(p['pub'], p['nxt'])[0, 1]:+.2f}")
stopped, won = p[p["pub"] < -35], p[p["pub"] > 0]
print(
    f"   {len(stopped)} published stops: {stopped['pub'].mean():.1f} points each; plain hold {stopped['nxt'].mean():.1f}"
)
print(
    f"   {len(won)} published winners: {won['pub'].mean():.1f} points each; plain hold {won['nxt'].mean():.1f}"
)
for a_, b_ in (("2025-07-01", "2025-12-31"), ("2026-01-01", "2026-08-31")):
    x = p[(p["ent"] >= a_) & (p["ent"] <= b_)]
    print(
        f"   {a_[:7]} to {b_[:7]}: published {x['pub'].sum():6.0f}, plain hold {x['nxt'].sum():6.0f} points ({len(x)} trades)"
    )
