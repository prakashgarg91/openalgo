"""Forward ledgers of the weekly call spread on made-up one-minute candles."""

import numpy as np
import pandas as pd

from services.algos import forward_weekly as fw
from services.algos.intraday import OptionBars

EXPIRY = pd.Timestamp("2026-11-10")  # a Tuesday
ENTRY_DAY = pd.Timestamp("2026-11-06")
SESSIONS = [ENTRY_DAY, pd.Timestamp("2026-11-09"), EXPIRY]


def minutes(day, start, end, value):
    idx = pd.date_range(
        day + pd.Timedelta(hours=start[0], minutes=start[1]),
        day + pd.Timedelta(hours=end[0], minutes=end[1]),
        freq="1min",
    )
    return pd.DataFrame(dict.fromkeys(("open", "high", "low", "close"), value), index=idx)


def leg(before, at_expiry, drop_entry_minute=False):
    frames = []
    for day in SESSIONS:
        if day == EXPIRY:
            frames.append(minutes(day, (9, 15), (15, 29), at_expiry))
        else:
            frames.append(minutes(day, (9, 15), (15, 29), before))
    frame = pd.concat(frames)
    if drop_entry_minute:
        frame = frame.drop(ENTRY_DAY + pd.Timedelta(hours=10, minutes=15))
    return frame


def bars(**long_kwargs):
    frames = {
        (EXPIRY, "CE", 25000.0): leg(20.0, 2.0),
        (EXPIRY, "CE", 25100.0): leg(5.0, 1.0, **long_kwargs),
        (EXPIRY, "CE", 25250.0): leg(3.0, 0.5),
    }
    return OptionBars(frames)


def index_1m(price=25010.0):
    days = [pd.Timestamp("2026-11-05"), *SESSIONS]
    return pd.concat([minutes(d, (9, 15), (15, 29), price) for d in days])


def vix(level=14.0):
    return pd.Series({pd.Timestamp("2026-11-05"): level, ENTRY_DAY: level})


def run(b=None, **kw):
    b = b or bars()
    return fw.run(b, index_1m(**kw), vix())


def test_a_complete_week_is_counted_with_the_new_lot_size_and_the_last_minute_candle():
    r = run()["L1"]
    assert len(r.trades) == 1 and not r.open_positions and not r.weeks_skipped
    t = r.trades[0]
    assert t["entry"] == pd.Timestamp("2026-11-06 10:15")
    assert t["exit"] == pd.Timestamp("2026-11-10 15:29")
    assert t["credit"] == 15.0 and t["exit_value"] == 1.0 and t["pts"] == 14.0
    assert t["lot"] == 65
    assert [(g["sold"], g["long"]) for g in t["legs"]] == [(25000.0, 25100.0)]


def test_the_reference_ledger_uses_the_wider_wing():
    t = run()["L2"].trades[0]
    assert [(g["sold"], g["long"]) for g in t["legs"]] == [(25000.0, 25250.0)]


def test_an_expiry_day_only_partly_stored_is_not_counted_and_never_left_open():
    cut = OptionBars(
        {
            k: v[~((v.index.normalize() == EXPIRY) & (v.index.time > pd.Timestamp("15:20").time()))]
            for k, v in bars()._frames.items()
        }
    )
    r = run(cut)["L1"]
    assert not r.trades and not r.open_positions
    assert r.weeks_skipped == [{"expiry": EXPIRY, "reason": "expiry day only partly stored"}]


def test_a_missing_candle_at_the_entry_minute_is_not_counted_and_never_filled_from_an_earlier_one():
    r = run(bars(drop_entry_minute=True))["L1"]
    assert not r.trades
    assert r.weeks_skipped == [{"expiry": EXPIRY, "reason": "no candle at the entry minute"}]


def test_weeks_before_the_first_counted_expiry_are_left_out():
    early = bars()
    from services.algos import condor

    r = condor.simulate_weekly(
        condor.S3, early, index_1m(), vix(), set(SESSIONS), width=100,
        last_bar=fw.LAST_CANDLE, first_expiry=pd.Timestamp("2026-11-17"),
    )  # fmt: skip
    assert not r.trades and not r.weeks_skipped


def test_a_week_whose_expiry_is_not_stored_yet_is_open_not_skipped():
    short = {}
    for key, frame in bars()._frames.items():
        short[key] = frame[frame.index.normalize() < pd.Timestamp("2026-11-10")]
    only_to_monday = OptionBars(short)
    # the contract is stored (it was captured from the entry day) but the expiry session is ahead
    r = fw.run(only_to_monday, index_1m(), vix())["L1"]
    assert not r.trades and not r.weeks_skipped
    assert len(r.open_positions) == 1
    held = r.open_positions[0]
    assert held["entry"] == pd.Timestamp("2026-11-06 10:15") and held["credit"] == 15.0
    assert pd.Timestamp("2026-11-09") in held["marks"]


def test_the_filters_still_apply():
    assert run()["L1"].trades
    high = fw.run(bars(), index_1m(), vix(25.0))["L1"]
    assert not high.trades and high.weeks_skipped[0]["reason"] == "vix ceiling"


def test_the_bootstrap_bound_is_fixed_and_reproducible():
    same = np.full(12, 100.0)
    assert fw.bootstrap_lower(same) == 100.0
    mixed = np.array([100.0, -50.0, 80.0, 120.0, -200.0, 90.0, 60.0, 70.0] * 3)
    assert fw.bootstrap_lower(mixed) == fw.bootstrap_lower(mixed)
    assert fw.bootstrap_lower(mixed) < mixed.mean()
    assert np.isnan(fw.bootstrap_lower(np.array([])))


def report(**over):
    base = {
        "completed": 26, "lowest_equity": -3000, "realistic_net": 5000, "realistic_net_2x": 2000,
        "drawdown": 4000, "worst_day": -1500, "boot_lower_mean": 5.0, "best_trade_removed": 100,
    }  # fmt: skip
    return {**base, **over}


def test_nothing_is_decided_before_the_end_except_the_stop():
    running = fw.decide(report(completed=10), pd.Timestamp("2026-12-01"))
    assert running["state"] == "running" and running["verdict"] is None
    assert running["trades_to_go"] == 16
    stopped = fw.decide(report(completed=10, lowest_equity=-20_000), pd.Timestamp("2026-12-01"))
    assert stopped["state"] == "stopped" and stopped["verdict"] == "fail"


def test_the_pass_rule_needs_every_gate():
    today = pd.Timestamp("2027-05-01")
    assert fw.decide(report(), today)["verdict"] == "pass"
    for field, bad in (
        ("realistic_net", -1), ("realistic_net_2x", -1), ("drawdown", 20_001),
        ("worst_day", -20_001), ("boot_lower_mean", -0.1), ("best_trade_removed", -5),
    ):  # fmt: skip
        assert fw.decide(report(**{field: bad}), today)["verdict"] == "fail", field


def test_too_few_trades_by_the_end_date_is_inconclusive_not_a_pass():
    assert fw.decide(report(completed=20), pd.Timestamp("2027-06-01"))["verdict"] == "inconclusive"


def test_the_report_is_written_for_both_ledgers_with_the_week_listed():
    b = bars()
    results = fw.run(b, index_1m(), vix())
    out = fw.build_report(results, index_1m(), b.days(), pd.Timestamp("2026-11-12"))
    one = out["ledgers"]["L1"]
    assert one["completed"] == 1 and one["trades"][0]["gap_days"] == 4
    assert out["ledgers"]["L2"]["width"] == 250
    assert one["status"]["state"] == "running"
    assert one["realistic_net"] == round(one["trades"][0]["net"])


def test_the_first_counted_week_is_the_holiday_shifted_one():
    """10 November 2026 is a market holiday, so the registered first week expires on Monday the 9th."""
    assert fw.FIRST_EXPIRY == pd.Timestamp("2026-11-09")
    assert (
        pd.Timestamp("2026-11-03") < fw.FIRST_EXPIRY
    )  # the week entered before registration stays out
