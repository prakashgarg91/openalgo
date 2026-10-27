"""Hold-to-expiry credit structures on REAL option prices.

Overnight trading pays costs every night for a small slice of time decay. Holding
to expiry earns the premium over several days and pays entry costs once; the
position then settles in cash, so there is no exit order. Entry is the contract's
real close k trading days before expiry; the exit is the cash settlement,
approximated by the Nifty close on expiry day.

Costs: entry slippage (a quarter point or 1 percent of premium per leg), brokerage,
STT on the premium sold, exchange fees, and STT on exercise (0.125 percent of the
intrinsic value) for long legs that finish in the money.

The grid is fixed in advance: condors, put spreads and iron flies, entered 2, 3 or
4 sessions before expiry. 2023-2024 is the first half and 2025 onward the second;
no parameter is chosen from the second half.

Usage:
    uv run python scripts/algo_backtest/real_expiry_hold.py <history_dir> <nse_days_dir>
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_data import load_dir  # noqa: E402

from services.algos import lab  # noqa: E402

LOT = 75
MODEL = lab.CONSERVATIVE
EXERCISE_STT = 0.00125
history = load_dir(sys.argv[1])
real = lab.load_real_prices(Path(sys.argv[2]))
spot = history.frames["nifty"]["Close"]
days = sorted(real._days)
expiries = sorted({e for d in days for e in real.expiries(d) if e <= days[-1]})
CUT = pd.Timestamp("2025-01-01")

SHAPES = {
    "condor": [(1, 3), (1, 4), (2, 4), (2, 5), (3, 5)],
    "bullput": [(1, 3), (1, 4), (2, 4), (2, 5), (3, 5)],
    "ironfly": [(0, 2), (0, 3), (0, 4)],
}


def legs_for(family, short, long_):
    if family == "condor":
        return [
            ("PE", -long_, False),
            ("CE", long_, False),
            ("PE", -short, True),
            ("CE", short, True),
        ]
    if family == "bullput":
        return [("PE", -long_, False), ("PE", -short, True)]
    return [("PE", -long_, False), ("CE", long_, False), ("PE", 0, True), ("CE", 0, True)]


def intrinsic(kind, strike, final):
    return max(final - strike, 0.0) if kind == "CE" else max(strike - final, 0.0)


def trade(family, short, long_, k, expiry):
    if expiry not in spot.index or expiry not in real._days:
        return None
    sessions = [d for d in days if d <= expiry]
    if len(sessions) <= k or sessions[-1] != expiry:
        return None
    entry_day = sessions[-1 - k]
    if (expiry - entry_day).days > 10 or entry_day not in spot.index:
        return None
    atm = round(float(spot.loc[entry_day]) / 50) * 50
    final = float(spot.loc[expiry])
    pts, slip_pts, sell_value, turnover, exercise = 0.0, 0.0, 0.0, 0.0, 0.0
    for kind, steps, short_leg in legs_for(family, short, long_):
        strike = atm + 50 * steps
        entry = real._price(entry_day, expiry, strike, kind, "close")
        if entry is None:
            return None
        settle = intrinsic(kind, strike, final)
        pts += (entry - settle) if short_leg else (settle - entry)
        slip_pts += max(MODEL.spread_floor_pts, MODEL.spread_pct * entry)
        turnover += entry
        if short_leg:
            sell_value += entry
        else:
            exercise += settle
    cost = (
        slip_pts * LOT
        + MODEL.brokerage / 2
        + sell_value * LOT * MODEL.stt_pct
        + turnover * LOT * MODEL.exchange_pct
        + exercise * LOT * EXERCISE_STT
    )
    return {"date": entry_day, "gross": pts * LOT, "cost": cost, "net": pts * LOT - cost}


def stats(rows):
    if not rows:
        return "no trades"
    net = [r["net"] for r in rows]
    m = lab.summarize(net)
    pf = "n/a" if m["profit_factor"] is None else f"{m['profit_factor']:.2f}"
    gross = sum(r["gross"] for r in rows) / len(rows)
    cost = sum(r["cost"] for r in rows) / len(rows)
    return (
        f"n={m['trades']:3d} win={m['win_rate']:4.1f}% avg={m['avg']:6.0f} PF={pf:>5s} "
        f"maxDD={m['max_drawdown']:8.0f} gross={gross:6.0f} cost={cost:4.0f}"
    )


print(f"Real prices {days[0].date()} to {days[-1].date()}, {len(expiries)} expiries\n")
results = []
for family, shapes in SHAPES.items():
    for short, long_ in shapes:
        for k in (2, 3, 4):
            rows = [t for e in expiries if (t := trade(family, short, long_, k, e))]
            first = [r for r in rows if r["date"] < CUT]
            second = [r for r in rows if r["date"] >= CUT]
            results.append((family, short, long_, k, rows, first, second))
            print(f"  {family:7s} OTM{short}/OTM{long_} k={k}  all: {stats(rows)}")
            print(f"{'':27s} 2023-24: {stats(first)}")
            print(f"{'':27s} 2025+  : {stats(second)}")

positive = [
    r
    for r in results
    if r[4] and sum(x["net"] for x in r[5]) > 0 and sum(x["net"] for x in r[6]) > 0
]
print(
    f"\nCONFIGURATIONS TRIED: {len(results)}; profitable (after costs) in BOTH halves: {len(positive)}"
)
gross_pos = sum(1 for r in results if r[4] and sum(x["gross"] for x in r[4]) > 0)
print(
    f"Configurations with a positive average gross edge over the whole period: {gross_pos} of {len(results)}"
)
for family, short, long_, k, rows, _first, _second in sorted(
    positive, key=lambda r: -sum(x["net"] for x in r[4])
)[:5]:
    print(
        f"  {family} OTM{short}/OTM{long_} k={k}: total net {sum(x['net'] for x in rows):.0f} per lot"
    )
