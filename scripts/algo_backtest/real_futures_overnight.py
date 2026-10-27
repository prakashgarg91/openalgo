"""Hold one Nifty futures lot overnight, on REAL futures prices.

Nifty's own history shows its return arriving overnight (about +0.10 percent a day
close to open against -0.06 percent from open to close). This tests whether that
can be traded: buy the near-month future at its close, sell it at the next open.
There is no option pricing model here; the prices are the contract's own.

Costs per round trip on one lot: brokerage Rs 40, STT 0.02 percent of the sale,
exchange charges 0.00173 percent each way, stamp duty 0.002 percent of the purchase,
and one point of slippage each way.

Needs the history from fetch_history.py and the futures days from
fetch_nse_options.py with FETCH_KIND=futures.

Usage:
    uv run python scripts/algo_backtest/real_futures_overnight.py <history_dir> <futures_days_dir>
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_data import load_dir  # noqa: E402

from services.algos import lab  # noqa: E402
from services.algos.context import MarketInputs, score_regime  # noqa: E402

LOT = 75
BROKERAGE, STT, EXCH, STAMP, SLIP_PTS = 40.0, 0.0002, 0.0000173, 0.00002, 1.0
history = load_dir(sys.argv[1])
frames = {}
for path in sorted(Path(sys.argv[2]).glob("*.csv")):
    f = pd.read_csv(path, parse_dates=["date", "expiry"])
    if len(f):
        frames[f["date"].iloc[0]] = f.set_index("expiry")
days = sorted(frames)
print(f"Futures days: {len(days)} ({days[0].date()} to {days[-1].date()})")


def cost(price_in, price_out):
    notional_in, notional_out = price_in * LOT, price_out * LOT
    return (
        BROKERAGE
        + notional_out * STT
        + (notional_in + notional_out) * EXCH
        + notional_in * STAMP
        + SLIP_PTS * 2 * LOT
    )


# Regime for each day, from the same inputs the live runner uses.
nifty = history.frames["nifty"]
close = nifty["Close"]
vix = history.frames["vix"]["Close"].reindex(nifty.index, method="ffill")
ma20 = close.rolling(20).mean()


def us(name):
    r = history.frames[name]["Close"].pct_change() * 100
    return r.reindex(nifty.index - pd.Timedelta(days=1), method="ffill").set_axis(nifty.index)


sp, nd, cr, dx = (us(n) for n in ("spx", "ndx", "crude", "dxy"))
rows = []
for i in range(len(days) - 1):
    t, t1 = days[i], days[i + 1]
    today, nxt = frames[t], frames[t1]
    expiries = sorted(e for e in today.index if e >= t)
    if not expiries:
        continue
    # Near month, but roll in the last three days so the position is in the liquid contract.
    contract = expiries[0] if (expiries[0] - t).days > 3 or len(expiries) == 1 else expiries[1]
    if contract not in nxt.index:
        continue
    e, x = today.loc[contract], nxt.loc[contract]
    e_close, x_open = float(e["close"]), float(x["open"])
    if e_close <= 0 or x_open <= 0 or float(e["volume"]) <= 0:
        continue
    gross = (x_open - e_close) * LOT
    c = cost(e_close, x_open)
    ix = nifty.index.get_loc(t) if t in nifty.index else None
    label = None
    if ix is not None and ix > 25:
        gap = (close.iloc[ix] / close.iloc[ix - 1] - 1) * 100
        v = float(vix.iloc[ix])
        regime = score_regime(
            MarketInputs(
                gap_pct=gap,
                sp500_pct=lab.num(sp.iloc[ix]),
                nasdaq_pct=lab.num(nd.iloc[ix]),
                crude_pct=lab.num(cr.iloc[ix]),
                dxy_pct=lab.num(dx.iloc[ix]),
                vix=v,
                vix_change_pct=(v / float(vix.iloc[ix - 1]) - 1) * 100,
                nifty_vs_ma20_pct=(close.iloc[ix] / ma20.iloc[ix] - 1) * 100,
            )
        )
        label = regime.label
    rows.append(
        {
            "date": t,
            "gross": gross,
            "cost": c,
            "net": gross - c,
            "weekday": t.day_name(),
            "regime": label,
        }
    )
df = pd.DataFrame(rows)


def show(title, d):
    if d.empty:
        print(f"{title}: no trades")
        return
    m = lab.summarize(list(d["net"]))
    pf = "n/a" if m["profit_factor"] is None else f"{m['profit_factor']:.2f}"
    sharpe = d["net"].mean() / d["net"].std() * np.sqrt(252) if d["net"].std() else 0
    print(
        f"{title:28s} n={m['trades']:4d} win={m['win_rate']:4.1f}% avgNet={m['avg']:6.0f} PF={pf:>5s} "
        f"gross={d['gross'].mean():6.0f} cost={d['cost'].mean():4.0f} maxDD={m['max_drawdown']:9.0f} "
        f"worst={m['worst']:8.0f} sharpe={sharpe:4.2f}"
    )


print()
show("All nights", df)
df["year"] = df["date"].dt.year
for y, g in df.groupby("year"):
    show(f"  {y}", g)
print()
for wd in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
    show(f"  entered on {wd}", df[df.weekday == wd])
print()
for label in ("calm", "trending", "volatile", "event"):
    show(f"  regime {label}", df[df.regime == label])
print()
show("Skip Fridays (weekends)", df[df.weekday != "Friday"])
show("Only calm and trending days", df[df.regime.isin(["calm", "trending"])])
first, second = df[df.date < "2025-01-01"], df[df.date >= "2025-01-01"]
print()
show("First half (2023-24)", first)
show("Second half (2025+)", second)
