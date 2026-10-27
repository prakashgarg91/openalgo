"""Morning-gap research with a train/test split. Not a promise.

A morning algo enters shortly after the open (about 09:25) when the opening gap
and the overnight US move are both visible, holds a credit spread, and exits
the same day (about 15:15). This script tests candidate rules the platform could
use, choosing the rule on 2018-2022 only and judging it on 2023 onward, which it
never saw. Baselines (always sell puts, always sell calls) show whether the gap
logic adds anything over harvesting drift and premium.

Modelled prices: Black-Scholes, India VIX as flat IV, entry at the open, exit at
the close, Rs 300 per lot costs. Not modelled: stops and targets, skew, real
fills, expiry-day behaviour (skipped), and the intraday path.

Usage:
    uv run python scripts/algo_backtest/run_morning_gap.py <data_dir>
"""

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import bs, expiry_after, num  # noqa: E402

from services.algos.context import MarketInputs, score_regime  # noqa: E402

D = sys.argv[1]
LOT, COST_PER_LOT = 75, 300.0
HOLD_YEARS = 0.25 / 365  # about 09:25 to 15:25
SHORT_N, LONG_N = 1, 4
TRAIN_END, MIN_TRAIN_TRADES = pd.Timestamp("2022-12-31"), 150
US_MOVE = 0.3  # percent, the overnight US move that counts as a signal


def load(name):
    df = pd.read_csv(f"{D}/{name}.csv", index_col=0, parse_dates=True)
    df.index = df.index.tz_localize(None) if df.index.tz else df.index
    return df


nifty, vix, spx, ndx, crude, dxy = (load(n) for n in ("nsei", "vix", "spx", "ndx", "crude", "dxy"))
nifty = nifty[nifty["Close"] > 0].dropna(subset=["Open", "Close"])
dates = nifty.index
opn, cls = nifty["Open"], nifty["Close"]
prev_close = cls.shift(1)
vopen = vix["Open"].reindex(dates, method="ffill")
vclose = vix["Close"].reindex(dates, method="ffill")
vprev = vclose.shift(1)


def us_ret(df):
    r = df["Close"].pct_change() * 100
    return r.reindex(dates - pd.Timedelta(days=1), method="ffill").set_axis(dates)


sp, nd, cr, dx = us_ret(spx), us_ret(ndx), us_ret(crude), us_ret(dxy)
trend = ((cls / cls.rolling(20).mean() - 1) * 100).shift(1)


def spread_points(i, side):
    """Points made by one credit spread entered at the open and closed at the close."""
    t = dates[i]
    exp = expiry_after(t)
    if (exp - t).days < 1:
        return None
    S0, S1 = float(opn.iloc[i]), float(cls.iloc[i])
    v0 = num(vopen.iloc[i])
    sig0 = (v0 if v0 and v0 > 0 else float(vprev.iloc[i])) / 100
    sig1 = float(vclose.iloc[i]) / 100
    T0 = (exp - t).days / 365
    atm = round(S0 / 50) * 50
    kind = "PE" if side == "bull_put" else "CE"
    sign = -1 if kind == "PE" else 1
    short_k, long_k = atm + sign * 50 * SHORT_N, atm + sign * 50 * LONG_N
    pts = 0.0
    for k, is_short in ((short_k, True), (long_k, False)):
        e = bs(S0, k, T0, sig0, kind)
        x = bs(S1, k, T0 - HOLD_YEARS, sig1, kind)
        pts += (e - x) if is_short else (x - e)
    return pts


def rule_side(rule, thr, gap, us):
    up, down = gap > thr, gap < -thr
    if rule == "always_bull_put":
        return "bull_put"
    if rule == "always_bear_call":
        return "bear_call"
    if rule == "fade":
        return "bear_call" if up else "bull_put" if down else None
    if rule == "follow":
        return "bull_put" if up else "bear_call" if down else None
    agree = (up and us > US_MOVE) or (down and us < -US_MOVE)
    diverge = (up and us < -US_MOVE) or (down and us > US_MOVE)
    if rule == "us_follow" and agree:
        return "bull_put" if up else "bear_call"
    if rule == "us_diverge_fade" and diverge:
        return "bear_call" if up else "bull_put"
    return None


rows = []
for i in range(25, len(dates)):
    t = dates[i]
    gap = (float(opn.iloc[i]) / float(prev_close.iloc[i]) - 1) * 100
    us = (num(sp.iloc[i]) or 0.0) + (num(nd.iloc[i]) or 0.0)
    us /= 2
    vchg = (num(vopen.iloc[i]) / float(vprev.iloc[i]) - 1) * 100 if num(vopen.iloc[i]) else None
    regime = score_regime(
        MarketInputs(
            gap_pct=gap,
            sp500_pct=num(sp.iloc[i]),
            nasdaq_pct=num(nd.iloc[i]),
            crude_pct=num(cr.iloc[i]),
            dxy_pct=num(dx.iloc[i]),
            vix=num(vopen.iloc[i]),
            vix_change_pct=vchg,
            nifty_vs_ma20_pct=num(trend.iloc[i]),
        )
    )
    cache = {}
    for rule in (
        "always_bull_put",
        "always_bear_call",
        "fade",
        "follow",
        "us_follow",
        "us_diverge_fade",
    ):
        for thr in (
            (0.2, 0.3, 0.5, 0.75) if rule not in ("always_bull_put", "always_bear_call") else (0.0,)
        ):
            side = rule_side(rule, thr, gap, us)
            if side is None:
                continue
            if side not in cache:
                cache[side] = spread_points(i, side)
            pts = cache[side]
            if pts is None:
                continue
            for gated in (False, True):
                if gated and regime.label not in ("calm", "trending"):
                    continue
                rows.append(
                    {
                        "date": t,
                        "rule": f"{rule}@{thr}{'+gate' if gated else ''}",
                        "base": rule,
                        "pnl": pts * LOT - COST_PER_LOT,
                    }
                )
df = pd.DataFrame(rows)
df.to_csv(f"{D}/morning_gap_trades.csv", index=False)


def metrics(x):
    if x.empty:
        return None
    cum = x["pnl"].cumsum()
    gp, gl = x.loc[x.pnl > 0, "pnl"].sum(), -x.loc[x.pnl < 0, "pnl"].sum()
    return {
        "n": len(x),
        "win": 100 * (x.pnl > 0).mean(),
        "avg": x.pnl.mean(),
        "tot": x.pnl.sum(),
        "dd": (cum - cum.cummax()).min(),
        "pf": gp / gl if gl else float("inf"),
    }


def fmt(m):
    if m is None:
        return "no trades"
    return (
        f"n={m['n']:4d} win={m['win']:4.1f}% avg={m['avg']:6.0f} tot={m['tot']:8.0f} "
        f"maxDD={m['dd']:8.0f} PF={m['pf']:4.2f}"
    )


train = df[df.date <= TRAIN_END]
test = df[df.date > TRAIN_END]
print(
    f"Train {train.date.min().date()} to {TRAIN_END.date()}, test {test.date.min().date()} to {test.date.max().date()}"
)
print(f"Rs per lot of {LOT} after Rs {COST_PER_LOT:.0f} costs, entry at open, exit at close\n")

train_m = {r: metrics(g) for r, g in train.groupby("rule")}
test_m = {r: metrics(g) for r, g in test.groupby("rule")}
signal_rules = [r for r in train_m if not r.startswith("always")]
eligible = [
    r for r in signal_rules if train_m[r]["n"] >= MIN_TRAIN_TRADES and train_m[r]["tot"] > 0
]
eligible.sort(key=lambda r: train_m[r]["pf"], reverse=True)

print("TRAIN: top 6 signal rules by profit factor (selection uses train only)")
for r in eligible[:6]:
    print(f"  {r:26s} {fmt(train_m[r])}")
print("TRAIN: baselines")
for r in sorted(r for r in train_m if r.startswith("always")):
    print(f"  {r:26s} {fmt(train_m[r])}")

winner = eligible[0] if eligible else None
print(f"\nSELECTED ON TRAIN: {winner}")
print("\nTEST (never seen during selection):")
if winner:
    print(f"  {winner:26s} {fmt(test_m.get(winner))}   <- selected")
for r in sorted(r for r in test_m if r.startswith("always")):
    print(f"  {r:26s} {fmt(test_m[r])}   <- baseline")

print("\nTEST: every signal rule, so the cost of selecting is visible")
beats = 0
for r in sorted(signal_rules, key=lambda r: -(test_m.get(r) or {"pf": 0})["pf"]):
    m = test_m.get(r)
    if m and m["n"] >= 80:
        beats += m["pf"] > 1.0
        print(f"  {r:26s} {fmt(m)}")
if winner and test_m.get(winner):
    print("\nWinner per test year (total Rs per lot, trades):")
    w = test[test.rule == winner].copy()
    w["year"] = w.date.dt.year
    for y, g in w.groupby("year"):
        print(f"  {y}: {g.pnl.sum():8.0f} over {len(g)} trades")
print(f"\nSignal rules with test PF above 1.0 (of those with 80+ test trades): {beats}")
