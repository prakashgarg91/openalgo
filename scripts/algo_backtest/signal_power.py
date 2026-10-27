"""Do the opening gap and the overnight US move predict the rest of the day?

Reports, for a train and a test period, the correlation and sign hit rate of
each cue against the open-to-close move. A cue with no predictive power cannot
carry a morning algo, whatever the option structure.

Usage:
    uv run python scripts/algo_backtest/signal_power.py <data_dir>
"""

import sys

import numpy as np
import pandas as pd

D = sys.argv[1]
SPLIT = pd.Timestamp("2022-12-31")
US_MOVE = 0.3


def load(name):
    df = pd.read_csv(f"{D}/{name}.csv", index_col=0, parse_dates=True)
    df.index = df.index.tz_localize(None) if df.index.tz else df.index
    return df


nifty = load("nsei")
nifty = nifty[nifty["Close"] > 0].dropna(subset=["Open", "Close"])
dates = nifty.index


def us_ret(name):
    r = load(name)["Close"].pct_change() * 100
    return r.reindex(dates - pd.Timedelta(days=1), method="ffill").set_axis(dates)


frame = pd.DataFrame(
    {
        "gap": (nifty["Open"] / nifty["Close"].shift(1) - 1) * 100,
        "us": (us_ret("spx") + us_ret("ndx")) / 2,
        "day": (nifty["Close"] / nifty["Open"] - 1) * 100,
        "prev_day": (nifty["Close"].shift(1) / nifty["Open"].shift(1) - 1) * 100,
    }
).dropna()

for label, part in (
    ("TRAIN 2018-2022", frame[frame.index <= SPLIT]),
    ("TEST 2023-2026", frame[frame.index > SPLIT]),
):
    print(f"\n{label}  ({len(part)} days)")
    print(
        f"  mean day move (open to close): {part.day.mean():+.3f}%   up days: {100 * (part.day > 0).mean():.1f}%"
    )
    print(f"  corr(gap, day move)        = {part.gap.corr(part.day):+.3f}")
    print(f"  corr(US move, day move)    = {part.us.corr(part.day):+.3f}")
    print(
        f"  corr(US move, gap)         = {part.us.corr(part.gap):+.3f}   (how much of the US move the open already holds)"
    )
    for thr in (0.3, 0.5, 0.75):
        big = part[part.gap.abs() > thr]
        if len(big) >= 30:
            follow = (np.sign(big.gap) == np.sign(big.day)).mean() * 100
            print(
                f"  |gap|>{thr}: n={len(big):3d}  day continues the gap {follow:4.1f}%   mean day move after gap up {big[big.gap > 0].day.mean():+.3f}%  after gap down {big[big.gap < 0].day.mean():+.3f}%"
            )
    strong_us = part[part.us.abs() > US_MOVE]
    hit = (np.sign(strong_us.us) == np.sign(strong_us.day)).mean() * 100
    print(
        f"  |US move|>{US_MOVE}: n={len(strong_us)}  day moves the same way as the US {hit:.1f}% of the time"
    )
