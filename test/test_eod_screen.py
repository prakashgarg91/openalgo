"""The end-of-day rejection-screen engine on made-up prices: geometry, filters, costs and gates."""

import numpy as np
import pandas as pd
import pytest

from services.algos import costs, nse_lots
from services.algos import eod_screen as es

E = pd.Timestamp("2021-05-13")  # a Thursday, weekly expiry, lot 75
M = pd.Timestamp("2021-05-27")  # the month's last Thursday
DAYS = [pd.Timestamp(d) for d in ("2021-05-10", "2021-05-11", "2021-05-12", "2021-05-13")]
ENTRY = pd.Timestamp("2021-05-11")  # two sessions before E


def premium(kind, strike, spot):
    intrinsic = max(spot - strike, 0.0) if kind == "CE" else max(strike - spot, 0.0)
    return intrinsic + max(1.0, 50.0 - abs(strike - spot) * 0.2)


def options(spot_by_day=None, settle_spot=24050.0, drop=None, expiries=(E,)):
    spot_by_day = spot_by_day or dict.fromkeys(DAYS, 24000.0)
    rows = []
    for expiry in expiries:
        for day in (*DAYS, *([expiry] if expiry not in DAYS else [])):
            for strike in range(23000, 25001, 50):
                for kind in ("CE", "PE"):
                    if drop and (day, expiry, kind, strike) in drop:
                        continue
                    spot = spot_by_day.get(day, 24000.0)
                    px = premium(kind, strike, spot)
                    if expiry == day:
                        px = (
                            max(settle_spot - strike, 0.0)
                            if kind == "CE"
                            else max(strike - settle_spot, 0.0)
                        )
                    rows.append({"date": day, "instrument": "OPTIDX", "expiry": expiry, "strike": float(strike),
                                 "kind": kind, "close": px, "settle": (settle_spot if expiry == day else px), "contracts": 100})  # fmt: skip
    return pd.DataFrame(rows)


def series(value, days=DAYS):
    return pd.Series(value, index=pd.DatetimeIndex(days))


def run(name, opts=None, vix=14.0, nifty=24000.0, first="2021-05-01", last="2021-06-30"):
    chain = es.Chain(opts if opts is not None else options())
    return es.simulate(es.SPECS[name], chain, series(nifty), series(vix), nse_lots.nifty_lot,
                       pd.Timestamp(first), pd.Timestamp(last))  # fmt: skip


def test_the_weekly_call_spread_sells_the_money_buys_100_above_and_uses_the_lot_by_expiry():
    result = run("WC")
    assert len(result.trades) == 1 and not result.skipped
    t = result.trades[0]
    assert t["entry"] == ENTRY and t["exit"] == E and t["lot"] == 75
    sold, bought = t["legs"]
    assert (sold["strike"], sold["side"]) == (24000, -1) and (bought["strike"], bought["side"]) == (
        24100,
        +1,
    )
    # entry credit 50 - 40 = 10 points; at expiry the 24000 call settles 50, the 24100 call 0
    assert t["pts"] == pytest.approx((50 - 50) + (0 - premium("CE", 24100, 24000)))
    assert t["net"] == pytest.approx(t["pts"] * 75 - t["cost"])
    assert t["net_2x"] == pytest.approx(t["pts"] * 75 - 2 * t["cost"])


def test_the_leg_costs_add_up_to_the_cost_schedule_every_other_test_uses():
    day, exit_day = pd.Timestamp("2025-03-03"), pd.Timestamp("2025-03-06")
    short = es.leg_cost(-1, 120.0, 30.0, day, exit_day, 75)
    long_ = es.leg_cost(+1, 60.0, 5.0, day, exit_day, 75)
    assert short + long_ == pytest.approx(
        costs.realistic_cost(day, exit_day, 120.0, 60.0, 30.0, 5.0, 75)
    )


def test_the_put_spread_and_the_condor_and_the_straddle_use_their_registered_strikes():
    wp = run("WP").trades[0]["legs"]
    assert [(g["kind"], g["strike"], g["side"]) for g in wp] == [
        ("PE", 24000, -1),
        ("PE", 23900, +1),
    ]
    wk = run("WK").trades[0]["legs"]
    assert [(g["kind"], g["strike"], g["side"]) for g in wk] == [
        ("CE", 24150, -1), ("CE", 24400, +1), ("PE", 23850, -1), ("PE", 23600, +1)
    ]  # fmt: skip
    st = run("STR").trades[0]
    assert [(g["kind"], g["strike"], g["side"]) for g in st["legs"]] == [
        ("CE", 24000, +1),
        ("PE", 24000, +1),
    ]
    assert st["pts"] == pytest.approx(
        50 + 0 - premium("CE", 24000, 24000) - premium("PE", 24000, 24000)
    )


def test_the_calendar_sells_the_weekly_and_buys_the_next_monthly_and_closes_it_at_the_weekly_expiry_close():
    both = pd.concat([options(), options(expiries=(M,))], ignore_index=True)
    t = run("CAL", opts=both).trades[0]
    near, far = t["legs"]
    assert (
        near["expiry"] == E
        and far["expiry"] == M
        and far["far"]
        and near["side"] == -1
        and far["side"] == +1
    )
    assert far["exit"] == pytest.approx(
        premium("CE", 24000, 24000)
    )  # the far leg is closed at that day's close, not at a settlement


def test_the_filters_skip_a_week_and_say_why():
    assert run("WC", vix=25.0).skipped[0]["reason"] == "vix ceiling"
    fall = {DAYS[0]: 24000.0, DAYS[1]: 23700.0, DAYS[2]: 23700.0, DAYS[3]: 23700.0}
    opts = options(spot_by_day=fall)
    nifty = pd.Series([24000.0, 23700.0, 23700.0, 23700.0], index=pd.DatetimeIndex(DAYS))
    chain = es.Chain(opts)
    args = (
        chain,
        nifty,
        series(14.0),
        nse_lots.nifty_lot,
        pd.Timestamp("2021-05-01"),
        pd.Timestamp("2021-06-30"),
    )
    assert (
        es.simulate(es.SPECS["WC"], *args).skipped[0]["reason"] == "one-day move filter"
    )  # fell 1.25 percent
    assert len(es.simulate(es.SPECS["WP"], *args).trades) == 1  # the put side only skips a rise
    assert (
        len(es.simulate(es.SPECS["WK"], *args).trades) == 1
    )  # the condor uses the VIX filter only


def test_a_leg_with_no_trade_at_the_entry_close_is_not_counted_and_never_filled_in():
    missing = {(ENTRY, E, "CE", 24100)}
    result = run("WC", opts=options(drop=missing))
    assert (
        not result.trades and result.skipped[0]["reason"] == "a leg has no trade at the entry close"
    )


def test_an_expiry_without_a_documented_lot_or_outside_the_period_is_left_out():
    early = es.Chain(options())
    old = es.simulate(es.SPECS["WC"], early, series(24000.0), series(14.0), lambda e: None,
                      pd.Timestamp("2021-05-01"), pd.Timestamp("2021-06-30"))  # fmt: skip
    assert old.skipped[0]["reason"] == "no documented lot size" and not old.trades
    assert not run("WC", first="2021-06-01", last="2021-06-30").trades


def test_a_missing_expiry_session_is_recorded():
    opts = options()
    opts = opts[opts["date"] != E]
    assert run("WC", opts=opts).trades == []


def test_equity_drawdown_and_the_bootstrap_are_exact_on_known_numbers():
    eq = pd.Series([100.0, 50.0, 80.0, -20.0, 40.0], index=pd.date_range("2021-01-01", periods=5))
    assert es.drawdown(eq) == 120.0 and es.worst_day(eq) == -100.0
    assert es.bootstrap_lower(np.full(12, 7.0)) == 7.0 and np.isnan(
        es.bootstrap_lower(np.array([]))
    )


def fake_trades(nets, nets2=None):
    start = pd.Timestamp("2021-01-04")
    out = []
    for i, n in enumerate(nets):
        out.append({"entry": start + pd.Timedelta(days=7 * i), "exit": start + pd.Timedelta(days=7 * i + 2),
                    "net": float(n), "net_2x": float(n if nets2 is None else nets2[i]), "marks": {}})  # fmt: skip
    return out


def sessions_for(trades):
    return [d for t in trades for d in (t["entry"], t["exit"])]


def test_every_gate_must_hold_and_the_verdict_is_only_eligible_or_rejected():
    good = fake_trades([200, 150, 180, 220] * 30)  # 120 trades, steady
    report = es.evaluate(es.Result("WC", trades=good), "weekly", sessions_for(good))
    assert report["verdict"] == "eligible for a forward test" and all(report["gates"].values())
    few = fake_trades([200] * 20)
    assert (
        es.evaluate(es.Result("WC", trades=few), "weekly", sessions_for(few))["gates"][
            "enough_trades"
        ]
        is False
    )
    assert (
        es.evaluate(es.Result("MC", trades=few), "monthly", sessions_for(few))["gates"][
            "enough_trades"
        ]
        is False
    )
    lumpy = fake_trades([5000] + [-10] * 120)  # one good trade carries it
    r = es.evaluate(es.Result("WC", trades=lumpy), "weekly", sessions_for(lumpy))
    assert r["gates"]["positive_without_best_trade"] is False and r["verdict"] == "rejected"
    flip = fake_trades([100] * 60 + [-90] * 60)  # positive overall, not in both halves
    assert (
        es.evaluate(es.Result("WC", trades=flip), "weekly", sessions_for(flip))["gates"][
            "positive_in_each_half"
        ]
        is False
    )
    thin = fake_trades([200, 150, 180, 220] * 30, nets2=[-1] * 120)  # dies at doubled costs
    assert (
        es.evaluate(es.Result("WC", trades=thin), "weekly", sessions_for(thin))["gates"][
            "net_positive_at_both_costs"
        ]
        is False
    )


def report_of(drawdown, net, verdict="eligible for a forward test"):
    return {"verdict": verdict, "stats": {"drawdown": drawdown, "net": net}}


def test_at_most_two_go_forward_smallest_drawdown_first_and_never_the_control():
    reports = {
        "WC": report_of(9000, 1000), "WP": report_of(4000, 500), "MK": report_of(4000, 900),
        "WK": report_of(1000, 100, "rejected"), "STR": report_of(100, 5000),
    }  # fmt: skip
    assert es.choose_survivors(reports) == ["MK", "WP"]  # ties broken by the larger net
    assert es.control_is_suspect(reports) is True
    assert es.control_is_suspect({"STR": report_of(100, 5, "rejected")}) is False
    assert es.choose_survivors({"WC": report_of(1, 1, "rejected")}) == []


def _script():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "algo_backtest"
        / "eight_structure_screen.py"
    )
    spec = importlib.util.spec_from_file_location("eight_structure_screen_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_screen_refuses_before_its_run_date_and_a_second_run_but_not_the_first_run_after_it():
    """Registered for 1 December 2026; brought forward to 2 November 2026 by the owner (dated note in the
    registration). It still runs once."""
    from datetime import date

    script = _script()
    assert "on or after 2 November 2026" in script.refusal(date(2026, 11, 1), False)
    assert script.refusal(date(2026, 11, 2), False) is None
    assert "already been run" in script.refusal(date(2026, 12, 2), True)
    assert "on or after 2 November 2026" in script.refusal(
        date(2026, 10, 30), True
    )  # the date comes first


def test_an_option_is_valued_at_expiry_from_the_index_settlement_not_from_the_settle_column_of_its_row():
    """On an expiry date the file's settle column is the INDEX's final price on every strike; the
    option's value is its intrinsic value against it. Real layout: close is the option's own close."""
    opts = options(settle_spot=24050.0)
    on_expiry = opts["date"] == E
    assert (opts.loc[on_expiry, "settle"] == 24050.0).all()  # the same number on every strike
    trade = run("WC", opts=opts).trades[0]
    sold, bought = trade["legs"]
    assert sold["exit"] == pytest.approx(50.0)  # 24050 - 24000, not 24050
    assert bought["exit"] == 0.0  # 24100 call is out of the money
    assert trade["pts"] == pytest.approx((50.0 - 50.0) + (0.0 - premium("CE", 24100, 24000.0)))
    straddle = run("STR", opts=opts).trades[0]
    assert [g["exit"] for g in straddle["legs"]] == [50.0, 0.0]  # call 50, put 0: never about 24000


def test_a_week_whose_expiry_rows_disagree_on_the_index_settlement_is_not_counted():
    opts = options()
    first = opts.index[(opts["date"] == E)][0]
    opts.loc[first, "settle"] = 99999.0  # one row says something else
    result = run("WC", opts=opts)
    assert (
        not result.trades
        and result.skipped[0]["reason"] == "no index settlement price on the expiry date"
    )


def test_a_calendar_whose_legs_have_different_lot_sizes_is_not_counted():
    both = pd.concat([options(), options(expiries=(M,))], ignore_index=True)
    chain = es.Chain(both)
    lots = lambda e: 75 if e == E else 50  # noqa: E731 (the near leg at 75, the far month already at 50)
    out = es.simulate(
        es.SPECS["CAL"],
        chain,
        series(24000.0),
        series(14.0),
        lots,
        pd.Timestamp("2021-05-01"),
        pd.Timestamp("2021-06-30"),
    )
    assert (
        not out.trades and out.skipped[0]["reason"] == "the legs' expiries have different lot sizes"
    )


def test_an_expiry_the_exchange_re_dated_is_not_in_the_expiry_list():
    """A holiday moved the 2021-05-20 expiry to the 19th: the contracts carry the new date, and no row
    sits on the old one. The old label must not stay in the list (it would shadow the real expiry)."""
    opts = options()
    old = opts.copy()
    old["expiry"] = pd.Timestamp(
        "2021-05-20"
    )  # the label before the move, rows only on earlier dates
    chain = es.Chain(pd.concat([opts, old], ignore_index=True))
    # last session stored is 05-13, so 05-20 is still in the future here: it stays, as a future expiry
    assert pd.Timestamp("2021-05-20") in chain.expiries
    later = options()
    later = later.assign(
        date=later["date"] + pd.Timedelta(days=14), expiry=later["expiry"] + pd.Timedelta(days=14)
    )
    chain2 = es.Chain(
        pd.concat([opts, old, later], ignore_index=True)
    )  # sessions now run past 05-20
    assert (
        pd.Timestamp("2021-05-20") not in chain2.expiries
    )  # in the past and never settled on its date
    assert pd.Timestamp("2021-05-13") in chain2.expiries


def test_a_session_missing_from_the_data_removes_the_week_instead_of_moving_the_entry_earlier():
    days = [
        pd.Timestamp(d)
        for d in ("2021-05-07", "2021-05-10", "2021-05-11", "2021-05-12", "2021-05-13")
    ]
    opts = options()
    extra = opts[opts["date"] == DAYS[0]].assign(date=days[0])
    stored = pd.concat([opts, extra], ignore_index=True)
    stored = stored[stored["date"] != DAYS[1]]  # the 11th, the real entry session, was never stored
    nifty = pd.Series(24000.0, index=pd.DatetimeIndex(days))
    vix = pd.Series(14.0, index=pd.DatetimeIndex(days))
    out = es.simulate(
        es.SPECS["WK"],
        es.Chain(stored),
        nifty,
        vix,
        nse_lots.nifty_lot,
        pd.Timestamp("2021-05-01"),
        pd.Timestamp("2021-06-30"),
    )
    assert not out.trades and out.skipped[0]["reason"] == "entry session was not stored"


def test_the_trading_calendar_can_be_given_and_names_the_entry_session():
    calendar = lambda d: pd.Timestamp(d).weekday() < 5  # noqa: E731
    out = es.simulate(
        es.SPECS["WK"],
        es.Chain(options()),
        series(24000.0),
        series(14.0),
        nse_lots.nifty_lot,
        pd.Timestamp("2021-05-01"),
        pd.Timestamp("2021-06-30"),
        calendar,
    )
    assert out.trades[0]["entry"] == ENTRY  # two weekdays before Thursday 13 May


def test_the_bootstrap_bar_is_the_one_it_is_given():
    trades = [{"entry": pd.Timestamp("2021-01-04") + pd.Timedelta(days=7 * i), "exit": pd.Timestamp("2021-01-06") + pd.Timedelta(days=7 * i), "net": 100.0 + 20 * (i % 3), "net_2x": 90.0, "marks": {}} for i in range(40)]  # fmt: skip
    result = es.Result("WC", trades=trades)
    sessions = [t[k] for t in trades for k in ("entry", "exit")]
    strict = es.evaluate(result, "weekly", sessions, min_trades=30)["stats"]["boot_lower_mean"]
    loose = es.evaluate(result, "weekly", sessions, min_trades=30, boot_level=0.4)["stats"][
        "boot_lower_mean"
    ]
    assert loose >= strict  # a looser level gives a higher lower bound: the argument is honoured


def test_the_split_by_the_markets_trailing_move_is_saved_with_every_trade_and_skip():
    close = pd.Series(
        range(100, 140), index=pd.date_range("2021-01-01", periods=40, freq="B"), dtype=float
    )
    falling = close[::-1].copy()
    falling.index = close.index
    t = [{"entry": close.index[30], "net": 100.0}]
    assert es.net_by_trailing_market(t, close) == {"falling": 0.0, "not_falling": 100.0}
    assert es.net_by_trailing_market(t, falling) == {"falling": 100.0, "not_falling": 0.0}
    rows = es.trade_rows(run("WC"))
    assert (
        rows["trades"][0]["entry"] == "2021-05-11"
        and rows["trades"][0]["legs"][0]["strike"] == 24000
    )
    assert rows["not_counted"] == []
