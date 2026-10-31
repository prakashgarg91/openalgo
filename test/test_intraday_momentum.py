"""Intraday momentum study: session building and the verification rule, on made-up minutes."""

import numpy as np
import pandas as pd

from scripts.algo_backtest import intraday_momentum_study as im


def minutes_for(days, drift_first=0.001, drift_last=0.0005, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    price = 20000.0
    for day in days:
        idx = pd.date_range(f"{day} 09:15", f"{day} 15:29", freq="1min")
        r = rng.normal(0, 0.0002, len(idx))
        r[:30] += drift_first / 30
        r[-30:] += drift_last / 30
        close = price * np.exp(np.cumsum(r))
        open_ = np.r_[price, close[:-1]]
        frames.append(
            pd.DataFrame({"open": open_, "high": close, "low": open_, "close": close}, index=idx)
        )
        price = float(close[-1])
    return pd.concat(frames)


def test_sessions_need_a_full_day_and_the_gap_needs_the_previous_full_day():
    days = pd.bdate_range("2025-01-06", periods=4).strftime("%Y-%m-%d")
    m = minutes_for(days)
    m = m[
        ~(
            (m.index.normalize() == pd.Timestamp(days[1]))
            & (m.index.time > pd.Timestamp("12:00").time())
        )
    ]
    s = im.session_returns(m)
    assert [d.strftime("%Y-%m-%d") for d in s.index] == [days[0], days[2], days[3]]
    assert (
        np.isnan(s["gap"].iloc[0]) and np.isnan(s["gap"].iloc[1]) and not np.isnan(s["gap"].iloc[2])
    )


def test_a_planted_relationship_is_found_and_marked_verified():
    days = pd.bdate_range("2023-01-02", periods=400).strftime("%Y-%m-%d")
    rng = np.random.default_rng(3)
    s = pd.DataFrame(index=pd.to_datetime(days))
    s["first30"] = rng.normal(0, 0.003, 400)
    s["prev30"] = rng.normal(0, 0.002, 400)
    s["gap"] = rng.normal(0, 0.004, 400)
    s["last30"] = 0.2 * s["first30"] + rng.normal(0, 0.001, 400)
    out = im.run(s, pd.Series(15.0, index=s.index))
    hit = [p for p in out["pairs"] if p["condition"] == "all" and p["predictor"] == "first30"][0]
    miss = [p for p in out["pairs"] if p["condition"] == "all" and p["predictor"] == "prev30"][0]
    assert hit["verified"] and not miss["verified"]
    assert out["joint_r2_second_half"] > 0.1


def test_expiry_flag_moves_from_thursday_to_tuesday():
    d = pd.DatetimeIndex(["2025-08-28", "2025-09-02", "2025-09-04"])
    assert list(im.expiry_flag(d)) == [True, True, False]
