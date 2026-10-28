"""Zen's reverse-engineered structure on real option prices, 2022 to 2026.

Structure taken from the published trade table (see stratzy_zen_reverse.py): a
400-point credit spread with the sold strike at the money, held from the morning
of one session to the close of the next, kept out of the market when India VIX
is high or the market gaps down hard. Its side rule is not published, so side
rules that use only what is known at the open are tried.

Pre-registered grid (fixed before any result was read), 48 cells:
  shape   Z   sold ATM, long 400 away      (published)
          O   sold 1 strike out, long 4 out, 150 wide  (what this platform trades)
          W   sold ATM, long 150 away       (isolates width from distance)
  side    put      always a bull put
          call     always a bear call
          lean     put when the prior close is below its 20-day average
          gap      put when the entry day closes at or above the prior close
  filter  none     every session
          zen      skip when India VIX is 20 or more, or the entry day is
                   down 1% or more
  expiry  near     nearest weekly expiry, expiry day included
          eve      nearest weekly expiry at least 2 days away

Entry is the CLOSE print of each contract on the entry day and exit the next
session's close (or intrinsic value if the contract has expired). The grid
cannot use opening prints: an option's first trade of the day lags the gapped
spot, so selling the side a gap favours looks free. The robustness section
shows that artefact (put-call parity off by about 46 points after a gap down
and minus 28 after a gap up at the open, flat at the close). Side rules that
read "the gap" therefore mean the entry day's close against the prior close.
One lot, conservative itemised costs, no stop and no target: daily prices
cannot replay either. Three periods are shown so a result that exists only in
one stretch is visible.

Usage:
    uv run python scripts/algo_backtest/stratzy_zen_method.py <history_dir> <nse_days_dir>
"""

import sys
from dataclasses import replace
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import lab  # noqa: E402

hist_dir, real_dir = Path(sys.argv[1]), Path(sys.argv[2])
real = lab.load_real_prices(real_dir)
nifty = pd.read_csv(hist_dir / "nsei.csv", parse_dates=["Date"]).set_index("Date")
vix = pd.read_csv(hist_dir / "vix.csv", parse_dates=["Date"]).set_index("Date")["Close"]
close, open_ = nifty["Close"], nifty["Open"]
sma20 = close.rolling(20).mean().shift(1)
prev_close, prev_vix = close.shift(1), vix.shift(1)
first, last = min(real._days), max(real._days)
sessions = [s for s in nifty.index if first <= s <= last]
nxt = {sessions[i]: sessions[i + 1] for i in range(len(sessions) - 1)}

SHAPES = {"Z": (0, 400), "O": (1, 200), "W": (0, 150)}  # (sold steps out, long distance from ATM)
SIDES = ["put", "call", "lean", "gap"]
FILTERS = ["none", "zen"]
EXPIRIES = ["near", "eve"]
SEGMENTS = [
    ("2022-01-01", "2023-06-30"),
    ("2023-07-01", "2024-12-31"),
    ("2025-01-01", "2026-12-31"),
]
ZEN_WINDOW = ("2025-07-09", "2026-08-28")


def leg_value(day, expiry, strike, kind, field):
    """A contract's real print, or its intrinsic value once expired; None when missing."""
    px = real._price(day, expiry, strike, kind, field)
    if px is not None:
        return px
    if pd.Timestamp(day) >= pd.Timestamp(expiry):
        s = float(close.get(pd.Timestamp(expiry), np.nan))
        if np.isnan(s):
            return None
        return max(0.0, strike - s) if kind == "PE" else max(0.0, s - strike)
    return None


def one_trade(
    t, shape, side_rule, filt, exp_rule, entry="open", exit_="close", model=None, min_gap=0.0
):
    t1 = nxt.get(t)
    if t1 is None or t not in prev_close.index:
        return None
    model = model or lab.CONSERVATIVE
    pc = float(prev_close[t])
    o = float(open_[t]) if entry == "open" else float(close[t])
    v = float(prev_vix.get(t, np.nan)) if entry == "open" else float(vix.get(t, np.nan))
    if filt == "zen" and (v >= 20 or o / pc - 1 <= -0.01):
        return None
    if abs(o / pc - 1) < min_gap:
        return None
    if side_rule == "put":
        side = "PE"
    elif side_rule == "call":
        side = "CE"
    elif side_rule == "lean":
        side = "PE" if pc < float(sma20[t]) else "CE"
    elif side_rule == "fade":
        side = "PE" if o < pc else "CE"
    else:
        side = "PE" if o >= pc else "CE"
    min_dte = 2 if exp_rule == "eve" else 0
    expiry = next((e for e in real.expiries(t) if (e - t).days >= min_dte), None)
    if expiry is None or (expiry - t).days > 8:
        return None
    steps, dist = SHAPES[shape]
    atm = round(o / 50) * 50
    sold = atm - 50 * steps if side == "PE" else atm + 50 * steps
    long_ = atm - dist if side == "PE" else atm + dist
    e_s = real._price(t, expiry, sold, side, entry)
    e_l = real._price(t, expiry, long_, side, entry)
    x_s = leg_value(t1, expiry, sold, side, exit_)
    x_l = leg_value(t1, expiry, long_, side, exit_)
    if None in (e_s, e_l, x_s, x_l):
        return None
    pts = (e_s - e_l) - (x_s - x_l)
    cost = lab.trade_cost(model, [e_s, e_l], [x_s, x_l], [True, False])
    return {"date": t, "side": side, "dte": (expiry - t).days, "net": pts * lab.LOT_SIZE - cost}


def stats(x):
    if len(x) == 0:
        return "n=  0"
    cum = np.cumsum(x)
    dd = float(np.min(cum - np.maximum.accumulate(np.r_[0.0, cum])[1:]))
    return f"n={len(x):3d} win={np.mean(np.array(x) > 0):4.0%} total={sum(x):8.0f} maxDD={dd:8.0f}"


def grid():
    print(
        f"Real prices {first.date()} to {last.date()}; {len(sessions)} sessions; lot size {lab.LOT_SIZE}\n"
    )
    cells = []
    for shape, side_rule, filt, exp_rule in product(SHAPES, SIDES, FILTERS, EXPIRIES):
        trades = [
            r
            for t in sessions
            if (r := one_trade(t, shape, side_rule, filt, exp_rule, entry="close"))
        ]
        df = pd.DataFrame(trades)
        name = f"{shape} {side_rule:4s} filter-{filt:4s} expiry-{exp_rule:4s}"
        segs = [df[(df["date"] >= a) & (df["date"] <= b)]["net"].tolist() for a, b in SEGMENTS]
        zen = df[(df["date"] >= ZEN_WINDOW[0]) & (df["date"] <= ZEN_WINDOW[1])]["net"].tolist()
        cells.append((name, df["net"].tolist(), segs, zen))
        print(name)
        print(f"  all    {stats(df['net'].tolist())}")
        for (a, b), s in zip(SEGMENTS, segs, strict=True):
            print(f"  {a[:7]}..{b[:7]} {stats(s)}")
        print(f"  zen window {stats(zen)}")

    lost = sum(1 for _, _, segs, _ in cells if segs[2] and sum(segs[2]) < 0)
    won_all = [c[0] for c in cells if all(s and sum(s) > 0 for s in c[2])]
    print(f"\n{len(cells)} cells tried; {lost} lost money in the untouched last period.")
    print(f"Cells profitable in all three periods: {len(won_all)}")
    for n in won_all:
        print("  ", n)


def run(label, **kw):
    shape, side_rule, filt, exp_rule = kw.pop("cell")
    rows = [r for t in sessions if (r := one_trade(t, shape, side_rule, filt, exp_rule, **kw))]
    df = pd.DataFrame(rows)
    segs = [df[(df["date"] >= a) & (df["date"] <= b)]["net"].tolist() for a, b in SEGMENTS]
    print(
        f"{label:44s} all {stats(df['net'].tolist())} | "
        + " | ".join(f"{sum(x):8.0f}" for x in segs)
    )
    return df


def robustness():
    print("Robustness (one lot; the last three columns are the three periods)\n")
    print("Does the entry print matter? Z shape, expiry near, no filter")
    for side in ("put", "call", "gap", "fade"):
        run(f"  {side:4s} enter at the open", cell=("Z", side, "none", "near"))
        run(
            f"  {side:4s} enter at the prior day's close",
            cell=("Z", side, "none", "near"),
            entry="close",
        )
    print("\nIs the gap rule just noise on tiny gaps? Z gap, filter zen, expiry near")
    for g in (0.0, 0.001, 0.003, 0.005):
        run(f"  skip gaps smaller than {g:.1%}", cell=("Z", "gap", "zen", "near"), min_gap=g)
    print("\nFill quality, Z gap, filter zen, expiry near")
    for mult in (1, 2, 3, 5):
        mdl = replace(
            lab.CONSERVATIVE,
            spread_floor_pts=lab.CONSERVATIVE.spread_floor_pts * mult,
            spread_pct=lab.CONSERVATIVE.spread_pct * mult,
        )
        run(f"  slippage x{mult}", cell=("Z", "gap", "zen", "near"), model=mdl)
    run("  exit at the next session's open", cell=("Z", "gap", "zen", "near"), exit_="open")
    df = run("  base", cell=("Z", "gap", "zen", "near"))
    print("\nWhere the base cell earns")
    print(
        "  by days to expiry:",
        {int(k): (len(v), round(v.sum())) for k, v in df.groupby("dte")["net"]},
    )
    print("  by side:", {k: (len(v), round(v.sum())) for k, v in df.groupby("side")["net"]})
    print(
        "  by year:",
        {int(k): (len(v), round(v.sum())) for k, v in df.groupby(df["date"].dt.year)["net"]},
    )
    n = df["net"]
    print(
        f"  worst trade {n.min():.0f}, best {n.max():.0f}, worst 5 trades together {n.nsmallest(5).sum():.0f}"
    )


if __name__ == "__main__":
    grid()
    print("\n" + "=" * 70 + "\n")
    robustness()
