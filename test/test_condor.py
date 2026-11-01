"""Weekly structures S2 to S4 on made-up 5-minute bars: entry day, strikes, hold to expiry, filters."""

import pandas as pd

from services.algos import condor
from services.algos.intraday import OptionBars

EXPIRY = pd.Timestamp("2025-11-11")  # a Tuesday
SESSIONS = [pd.Timestamp("2025-11-07"), pd.Timestamp("2025-11-10"), EXPIRY]


def five_minute(price_before, price_expiry):
    """Constant prices on the two sessions before expiry, another constant on the expiry session."""
    frames = []
    for day in SESSIONS:
        idx = pd.date_range(
            day + pd.Timedelta(hours=9, minutes=15),
            day + pd.Timedelta(hours=15, minutes=25),
            freq="5min",
        )
        value = price_expiry if day == EXPIRY else price_before
        frames.append(
            pd.DataFrame(dict.fromkeys(("open", "high", "low", "close"), value), index=idx)
        )
    return pd.concat(frames)


def bars():
    frames = {}
    for kind, sold, long_ in (("CE", 25150, 25400), ("PE", 24850, 24600), ("CE", 25000, 25250)):
        frames[(EXPIRY, kind, float(sold))] = five_minute(20.0, 2.0)
        frames[(EXPIRY, kind, float(long_))] = five_minute(5.0, 1.0)
    return OptionBars(frames)


def index_1m(price=25010.0):
    days = [pd.Timestamp("2025-11-06"), *SESSIONS]
    frames = []
    for day in days:
        idx = pd.date_range(
            day + pd.Timedelta(hours=9, minutes=15),
            day + pd.Timedelta(hours=15, minutes=29),
            freq="1min",
        )
        frames.append(
            pd.DataFrame(dict.fromkeys(("open", "high", "low", "close"), price), index=idx)
        )
    return pd.concat(frames)


def vix(level=14.0):
    return pd.Series(
        {
            pd.Timestamp("2025-11-06"): level,
            pd.Timestamp("2025-11-07"): level,
            pd.Timestamp("2025-11-10"): level,
        }
    )


def run(spec, level=14.0, allowed=None):
    return condor.simulate_weekly(spec, bars(), index_1m(), vix(level), allowed or set(SESSIONS))


def test_the_condor_enters_two_sessions_before_expiry_with_the_registered_strikes_and_holds_to_expiry():
    r = run(condor.S2)
    assert len(r.trades) == 1
    t = r.trades[0]
    assert t["entry"] == pd.Timestamp("2025-11-07 10:15")
    assert t["exit"] == pd.Timestamp("2025-11-11 15:25")
    strikes = {(leg["kind"], leg["sold"], leg["long"]) for leg in t["legs"]}
    assert strikes == {("CE", 25150.0, 25400.0), ("PE", 24850.0, 24600.0)}
    assert t["credit"] == 30.0 and t["exit_value"] == 2.0 and t["pts"] == 28.0
    assert t["lot"] == 75 and abs(t["net"] - (28 * 75 - t["cost"])) < 1e-9
    assert pd.Timestamp("2025-11-11") in t["marks"]


def test_the_weekly_call_spread_is_one_spread_at_the_money_and_the_late_condor_enters_one_session_before():
    t3 = run(condor.S3).trades[0]
    assert [(leg["kind"], leg["sold"], leg["long"]) for leg in t3["legs"]] == [
        ("CE", 25000.0, 25250.0)
    ]
    assert t3["credit"] == 15.0
    t4 = run(condor.S4).trades[0]
    assert t4["entry"] == pd.Timestamp("2025-11-10 14:30")


def test_filters_and_period_leave_the_week_out_and_say_why():
    high = run(condor.S2, level=25.0)
    assert not high.trades and high.skipped["vix ceiling"] == 1
    outside = run(condor.S2, allowed={pd.Timestamp("2025-11-10")})
    assert not outside.trades  # the entry session is the 7th, which is not in the period
