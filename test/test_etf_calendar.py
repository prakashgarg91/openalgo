"""C1, the month-end ETF window: buy three sessions before the last session, sell on the third session
of the next month (docs/algos/c1-registration.md). Calendar only; no price decides anything."""

import numpy as np
import pandas as pd
import pytest

from services.algos import etf_ledger as el

N, G = el.NIFTY, el.GOLD


def sessions(start, end):
    return pd.bdate_range(start, end)


def closes_for(index):
    n = len(index)
    return pd.DataFrame(
        {N: 100.0 + np.arange(n) * 0.05, G: np.full(n, 50.0)},
        index=index,
    )


def trade_days(rows):
    moved = rows[(rows["buy_notional"] > 0) | (rows["sell_notional"] > 0)]
    return list(moved["session"]), moved


def test_it_buys_three_sessions_before_the_months_last_session_and_sells_on_the_third_of_next_month():
    index = sessions("2026-10-01", "2026-12-31")
    rows = el.run_ledger("c1_calendar", closes_for(index), "2026-10-30").rows
    days, moved = trade_days(rows)
    nov = index[index.month == 11]
    dec = index[index.month == 12]
    assert days == [nov[-4], dec[2]]
    assert moved.iloc[0]["buy_notional"] > 0 and moved.iloc[1]["sell_notional"] > 0
    assert rows["nifty_shares"].iloc[-1] == 0  # flat after the sale


def test_it_never_spends_more_than_the_registered_amount_and_keeps_shares_whole():
    index = sessions("2026-10-01", "2026-12-31")
    rows = el.run_ledger("c1_calendar", closes_for(index), "2026-10-30").rows
    _, moved = trade_days(rows)
    bought = moved.iloc[0]
    assert (
        bought["buy_notional"]
        + (el.CAPITAL - rows.loc[bought.name, "cash"] - bought["buy_notional"])
        <= 19_000
    )
    assert float(bought["nifty_shares"]).is_integer()
    assert bought["nifty_shares"] * bought["nifty_close"] <= 19_000


def test_a_month_that_is_not_finished_in_the_data_makes_no_entry():
    index = sessions("2026-10-01", "2026-11-27")  # November's last session is not stored yet
    rows = el.run_ledger("c1_calendar", closes_for(index), "2026-10-30").rows
    days, _ = trade_days(rows)
    assert days == []  # the calendar cannot be read until the next month's first session is stored


def test_it_does_not_trade_again_while_holding_and_makes_one_round_trip_a_month():
    index = sessions("2026-10-01", "2027-03-31")
    rows = el.run_ledger("c1_calendar", closes_for(index), "2026-10-30").rows
    days, moved = trade_days(rows)
    buys = moved[moved["buy_notional"] > 0]
    sells = moved[moved["sell_notional"] > 0]
    assert len(buys) == 4 and len(sells) == 4  # Nov to Feb entries, each sold in the next month
    assert all(
        later > earlier for earlier, later in zip(days[:-1], days[1:], strict=True)
    )  # entries and exits alternate in order


def test_the_decision_uses_no_price():
    index = sessions("2026-10-01", "2026-12-31")
    up = closes_for(index)
    down = up.copy()
    down[N] = 200.0 - np.arange(len(index)) * 0.05
    a = el.run_ledger("c1_calendar", up, "2026-10-30").rows
    b = el.run_ledger("c1_calendar", down, "2026-10-30").rows
    assert trade_days(a)[0] == trade_days(b)[0]  # the same days whatever the prices did


def test_it_is_part_of_the_ledger_set_in_both_cost_variants():
    assert "c1_calendar" in el.all_rules()
    index = sessions("2026-10-01", "2026-12-31")
    ledgers = el.run_all(closes_for(index), "2026-10-30")
    assert "c1_calendar:base" in ledgers and "c1_calendar:double" in ledgers
    base = ledgers["c1_calendar:base"].rows["cumulative_cost"].iloc[-1]
    double = ledgers["c1_calendar:double"].rows["cumulative_cost"].iloc[-1]
    assert double > 1.9 * base > 0


@pytest.mark.parametrize("holiday_shift", [0, 1])
def test_a_missing_session_in_the_data_moves_the_dates_with_the_calendar(holiday_shift):
    index = sessions("2026-10-01", "2026-12-31")
    if holiday_shift:
        index = index.delete(list(index).index(pd.Timestamp("2026-11-26")))  # a shut day
    rows = el.run_ledger("c1_calendar", closes_for(index), "2026-10-30").rows
    days, _ = trade_days(rows)
    nov = index[index.month == 11]
    assert days[0] == nov[-4]
