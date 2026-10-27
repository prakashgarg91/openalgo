"""Indicative backtest of the production regime rules. Not a promise.

Prices the legs with Black-Scholes, India VIX as flat IV, enters at the close
and exits at the next open. Imports the real score_regime and build, so it
tests the rules the platform runs.

Usage:
    uv run python scripts/algo_backtest/fetch_history.py <data_dir>
    uv run python scripts/algo_backtest/run_backtest.py <data_dir>

What it does not model: stop losses and targets (only the next-open mark),
skew, real bid-ask on far strikes, margin, holiday expiry shifts, and the real
09:45 fill. Treat the output as a sanity check on the rules, not as returns.
"""

import math
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos.context import MarketInputs, RegimeResult, score_regime
from services.algos.templates import build

D = sys.argv[1]
LOT, CAP, COST_PER_LOT, R = 75, 500_000, 300.0, 0.065


def load(n):
    df = pd.read_csv(f"{D}/{n}.csv", index_col=0, parse_dates=True)
    df.index = df.index.tz_localize(None) if df.index.tz else df.index
    return df


nifty, vix, spx, ndx, crude, dxy = (load(n) for n in ("nsei", "vix", "spx", "ndx", "crude", "dxy"))
nifty = nifty[nifty["Close"] > 0].dropna(subset=["Open", "Close"])
dates = nifty.index


def asof_ret(df):
    r = df["Close"].pct_change() * 100
    return r.reindex(dates - pd.Timedelta(days=1), method="ffill").set_axis(dates)


g = {k: asof_ret(v) for k, v in {"sp": spx, "nd": ndx, "cr": crude, "dx": dxy}.items()}
vclose = vix["Close"].reindex(dates, method="ffill")
vopen = vix["Open"].reindex(dates, method="ffill")
close = nifty["Close"]
gap = close.pct_change() * 100
vchg = vclose.pct_change() * 100
ma20 = close.rolling(20).mean()
trend = (close / ma20 - 1) * 100


def _num(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, sig, kind):
    if T <= 0 or sig <= 0:
        return max(S - K, 0) if kind == "CE" else max(K - S, 0)
    d1 = (math.log(S / K) + (R + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if kind == "CE":
        return S * ncdf(d1) - K * math.exp(-R * T) * ncdf(d2)
    return K * math.exp(-R * T) * ncdf(-d2) - S * ncdf(-d1)


def expiry_after(t):
    wd = 1 if t >= pd.Timestamp("2025-09-01") else 3  # Tue since Sep 2025, else Thu
    ahead = (wd - t.weekday()) % 7
    return t + timedelta(days=ahead)


rows = []
for i in range(25, len(dates) - 1):
    t, t1 = dates[i], dates[i + 1]
    vals = [
        gap.iloc[i],
        g["sp"].iloc[i],
        g["nd"].iloc[i],
        g["cr"].iloc[i],
        g["dx"].iloc[i],
        vclose.iloc[i],
        vchg.iloc[i],
        trend.iloc[i],
    ]
    mi = MarketInputs(*(_num(v) for v in vals))
    regime = score_regime(mi)
    exp = expiry_after(t)
    dte = (exp - t).days
    S, S1 = float(close.iloc[i]), float(nifty["Open"].iloc[i + 1])
    atm = round(S / 50) * 50
    sig0 = float(vclose.iloc[i]) / 100
    v1 = float(vopen.iloc[i + 1])
    sig1 = (v1 if v1 > 0 and not math.isnan(v1) else float(vclose.iloc[i])) / 100
    for algo in ("zen", "mirror_zen", "calm_condor"):
        for gated in (True, False):
            rg = (
                regime
                if gated
                else RegimeResult(
                    "trending" if algo == "mirror_zen" else "calm",
                    regime.bias,
                    regime.score,
                    1.0,
                    (),
                    (),
                )
            )
            plan = build(algo, rg, capital=CAP, lot_size=LOT, days_to_expiry=dte)
            if plan.action != "trade":
                continue
            exp_use = exp if dte > 1 else exp + timedelta(days=7)
            T0 = (exp_use - t).days / 365
            T1 = (exp_use - t1).days / 365
            pts = 0.0
            for leg in plan.config["legs"]:
                n = int(leg["atm_offset"].replace("OTM", ""))
                K = atm + 50 * n if leg["option_type"] == "CE" else atm - 50 * n
                e = bs(S, K, T0, sig0, leg["option_type"])
                x = bs(S1, K, T1, sig1, leg["option_type"])
                pts += (x - e) if leg["position"] == "B" else (e - x)
            rows.append(
                {
                    "date": t,
                    "algo": algo,
                    "gated": gated,
                    "regime": regime.label,
                    "side": plan.side,
                    "pnl": pts * LOT - COST_PER_LOT,
                }
            )
df = pd.DataFrame(rows)
df.to_csv(f"{D}/trades.csv", index=False)


def stats(x):
    if x.empty:
        return "no trades"
    cum = x["pnl"].cumsum()
    dd = (cum - cum.cummax()).min()
    gp, gl = x.loc[x.pnl > 0, "pnl"].sum(), -x.loc[x.pnl < 0, "pnl"].sum()
    return (
        f"n={len(x):4d} win={100 * (x.pnl > 0).mean():4.1f}% avg={x.pnl.mean():7.0f} "
        f"tot/lot={x.pnl.sum():9.0f} maxDD/lot={dd:8.0f} worst={x.pnl.min():7.0f} "
        f"PF={gp / gl if gl else float('inf'):4.2f}"
    )


print(
    f"Days: {len(dates) - 26}  Range: {dates[25].date()} to {dates[-2].date()}  (Rs per lot of {LOT}, after Rs {COST_PER_LOT:.0f} costs)\n"
)
for algo in ("zen", "mirror_zen", "calm_condor"):
    for gated in (True, False):
        print(
            f"{algo:12s} {'REGIME-GATED' if gated else 'ungated     '} {stats(df[(df.algo == algo) & (df.gated == gated)])}"
        )
    print()
print("Regime-gated, by regime the trade was taken in:")
for algo in ("zen", "mirror_zen", "calm_condor"):
    for lab in ("calm", "trending"):
        x = df[(df.algo == algo) & df.gated & (df.regime == lab)]
        if len(x):
            print(f"  {algo:12s} {lab:9s} {stats(x)}")
print("\nWhat UNGATED Zen would have made on the days the platform stands aside:")
for lab in ("volatile", "event"):
    x = df[(df.algo == "zen") & (~df.gated) & (df.regime == lab)]
    print(f"  {lab:9s} {stats(x)}")
print("\nRegime-gated per year (total Rs per lot):")
df["year"] = df.date.dt.year
print(
    df[df.gated]
    .pivot_table(index="year", columns="algo", values="pnl", aggfunc="sum")
    .round(0)
    .to_string()
)
print("\nDays by regime label (share):")
labs = pd.Series(
    [
        score_regime(
            MarketInputs(
                *(
                    None if (isinstance(v, float) and math.isnan(v)) else float(v)
                    for v in (
                        gap.iloc[i],
                        g["sp"].iloc[i],
                        g["nd"].iloc[i],
                        g["cr"].iloc[i],
                        g["dx"].iloc[i],
                        vclose.iloc[i],
                        vchg.iloc[i],
                        trend.iloc[i],
                    )
                )
            )
        ).label
        for i in range(25, len(dates) - 1)
    ]
)
print((labs.value_counts(normalize=True) * 100).round(1).to_string())

print("\nMirror Zen if it were allowed on every day (ungated), by the regime of the day:")
for lab in ("calm", "trending", "volatile", "event"):
    x = df[(df.algo == "mirror_zen") & (~df.gated) & (df.regime == lab)]
    print(f"  {lab:9s} {stats(x)}")
print(
    "\nZen (follows the lean) vs Mirror Zen (fades it), ungated, trending days only, split by lean:"
)
for side in ("bull_put", "bear_call"):
    for algo in ("zen", "mirror_zen"):
        x = df[(df.algo == algo) & (~df.gated) & (df.regime == "trending") & (df.side == side)]
        print(f"  {algo:10s} {side:9s} {stats(x)}")
