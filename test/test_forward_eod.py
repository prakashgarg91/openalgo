"""Forward ledger for a registered end-of-day structure: settings, pending weeks, kill rule, verdicts."""

import pandas as pd
import pytest

from services.algos import eod_screen as es
from services.algos import forward_eod as fe
from services.algos import nse_lots

E = pd.Timestamp("2021-05-13")
E2 = pd.Timestamp("2021-05-20")  # a later expiry whose session is not stored
DAYS = [pd.Timestamp(d) for d in ("2021-05-10", "2021-05-11", "2021-05-12", "2021-05-13")]


def premium(kind, strike, spot):
    intrinsic = max(spot - strike, 0.0) if kind == "CE" else max(strike - spot, 0.0)
    return intrinsic + max(1.0, 50.0 - abs(strike - spot) * 0.2)


def options(expiries=(E,), settle_spot=24050.0):
    rows = []
    for expiry in expiries:
        for day in DAYS:
            for strike in range(23000, 25001, 50):
                for kind in ("CE", "PE"):
                    px = premium(kind, strike, 24000.0)
                    if expiry == day:
                        px = (
                            max(settle_spot - strike, 0.0)
                            if kind == "CE"
                            else max(strike - settle_spot, 0.0)
                        )
                    rows.append({"date": day, "instrument": "OPTIDX", "expiry": expiry, "strike": float(strike),
                                 "kind": kind, "close": px, "settle": (settle_spot if expiry == day else px), "contracts": 100})  # fmt: skip
    return pd.DataFrame(rows)


def registration(status="eligible for a forward test", ran="2021-04-20T10:00:00", **params):
    base = {"structure": "WC", "first_expiry": "2021-05-01", "end_trades": 26}
    return {
        "status": status,
        "run": {"at": ran} if ran else None,
        "content": {"params": {**base, **params}},
    }


def series(v):
    return pd.Series(v, index=pd.DatetimeIndex(DAYS))


def settings(**over):
    return {**fe.parse(registration()), **over}


def test_only_an_eligible_registration_that_names_a_structure_and_a_first_expiry_is_read():
    assert fe.parse(registration("registered")) is None
    assert fe.parse(registration(structure="XX")) is None
    assert (
        fe.parse(
            {"status": "eligible for a forward test", "content": {"params": {"structure": "WC"}}}
        )
        is None
    )
    got = fe.parse(registration(end_date="2027-05-31", kill_net=-5000))
    assert got["structure"] == "WC" and got["end_trades"] == 26 and got["kill_net"] == -5000.0
    assert got["end_date"] == pd.Timestamp("2027-05-31")


def test_a_running_test_counts_completed_weeks_and_lists_future_expiries_as_pending_not_lost():
    chain = es.Chain(pd.concat([options(), options((E2,))], ignore_index=True))
    s = settings()
    result = fe.run(s, chain, series(24000.0), series(14.0), nse_lots.nifty_lot)
    out = fe.report(s, result, chain.sessions, pd.Timestamp("2021-05-14"))
    assert out["state"] == "running" and out["verdict"] is None
    assert out["completed"] == 1 and out["trades_to_go"] == 25
    assert out["pending_expiries"] == ["2021-05-20"] and out["not_counted"] == []


def fake(nets):
    start = pd.Timestamp("2021-06-03")
    return es.Result(
        "WC",
        trades=[
            {"entry": start + pd.Timedelta(days=7 * i), "exit": start + pd.Timedelta(days=7 * i + 2),
             "expiry": start + pd.Timedelta(days=7 * i + 2), "lot": 75, "pts": n / 75, "marks": {},
             "net": float(n), "net_2x": float(n) * 0.9}
            for i, n in enumerate(nets)
        ],
    )  # fmt: skip


def sessions_of(result):
    return [d for t in result.trades for d in (t["entry"], t["exit"])]


def test_the_kill_rule_stops_the_test_and_records_a_fail():
    result = fake([-9000, -9000, -9000])
    out = fe.report(settings(), result, sessions_of(result), pd.Timestamp("2021-08-01"))
    assert (
        out["state"] == "stopped"
        and out["verdict"] == "fail"
        and out["lowest_cumulative_net"] == -27000
    )


def test_a_steady_run_that_reaches_its_trade_count_passes_every_gate():
    result = fake([200, 150, 180, 220] * 8)  # 32 trades
    out = fe.report(
        settings(end_trades=30), result, sessions_of(result), pd.Timestamp("2021-12-01")
    )
    assert out["state"] == "finished" and out["verdict"] == "pass" and all(out["gates"].values())


def test_a_lumpy_run_that_reaches_its_trade_count_fails_and_too_few_by_the_end_date_is_inconclusive():
    lumpy = fake([5000] + [-10] * 30)
    out = fe.report(settings(end_trades=30), lumpy, sessions_of(lumpy), pd.Timestamp("2021-12-01"))
    assert out["state"] == "finished" and out["verdict"] == "fail"
    few = fake([200, 150, 180])
    late = fe.report(
        settings(end_date=pd.Timestamp("2021-07-01")),
        few,
        sessions_of(few),
        pd.Timestamp("2021-07-02"),
    )
    assert late["state"] == "finished" and late["verdict"] == "inconclusive"
    early = fe.report(
        settings(end_date=pd.Timestamp("2021-07-01")),
        few,
        sessions_of(few),
        pd.Timestamp("2021-06-20"),
    )
    assert early["state"] == "running"


def test_the_report_has_no_verdict_before_the_end_even_when_every_week_won():
    result = fake([300] * 10)
    out = fe.report(settings(), result, sessions_of(result), pd.Timestamp("2021-09-01"))
    assert out["state"] == "running" and out["verdict"] is None
    with pytest.raises(KeyError):
        out["edge"]
