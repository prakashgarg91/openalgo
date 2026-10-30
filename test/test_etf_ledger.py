"""Shadow ledgers for the registered ETF ideas: timing, accounting, boundaries, replay match, determinism."""

import numpy as np
import pandas as pd
import pytest

from services.algos import etf_ledger as el
from services.algos import universe as u

N, G = el.NIFTY, el.GOLD


def closes(days=600, seed=3, start="2023-01-02"):
    idx = pd.bdate_range(start, periods=days)
    out = {}
    for name, s in ((N, seed), (G, seed + 9)):
        r = np.random.default_rng(s).normal(0.0004, 0.01, days)
        out[name] = 100 * np.exp(np.cumsum(r))
    return pd.DataFrame(out, index=idx)


def flat(days=40):
    idx = pd.bdate_range("2024-01-01", periods=days)
    return pd.DataFrame({N: 100.0, G: 50.0}, index=idx)


def test_a_signal_cannot_touch_the_holdings_of_the_close_that_made_it():
    c = flat(260)
    c.iloc[-3:, 0] = (
        200.0  # the Nifty ETF jumps over its 100-day average on the third-from-last close
    )
    led = el.run_ledger("idea2", c, str(c.index[120].date()))
    rows = led.rows.set_index("session")
    jump_day, after = c.index[-3], c.index[-2]
    assert rows.loc[jump_day, "nifty_shares"] == 0  # a close cannot trade itself
    assert rows.loc[after, "nifty_shares"] > 0  # the next close acts on it


def test_flat_prices_only_cost_the_itemised_charges_and_shares_stay_whole():
    c = flat(60)
    led = el.run_ledger("hold_5050", c, str(c.index[5].date()))
    rows = led.rows
    last = rows.iloc[-1]
    assert last["nav"] == pytest.approx(el.CAPITAL - last["cumulative_cost"])
    assert (rows["cash"] >= 0).all()
    assert rows["nifty_shares"].dtype.kind == "i"
    # Rs 50,000 and Rs 50,000 cannot also pay the charges out of Rs 1,00,000: the tie on the largest
    # buy and scaling take a few shares off, as the accounting rule says.
    assert 495 <= last["nifty_shares"] <= 499 and 990 <= last["gold_shares"] <= 1000
    assert last["cash"] < 0.01 * el.CAPITAL  # what is left over is idle cash, never negative
    assert (
        rows["cumulative_cost"].iloc[0] > 0
        and rows["cumulative_cost"].iloc[-1] == rows["cumulative_cost"].iloc[0]
    )


def test_the_first_trade_is_the_close_after_the_first_signal_date_and_starts_from_cash():
    c = flat(30)
    start = str(c.index[10].date())
    rows = el.run_ledger("hold_4040_cash", c, start).rows
    assert rows["session"].iloc[0] == c.index[11]
    assert rows.iloc[0]["nifty_shares"] == 400 and rows.iloc[0]["gold_shares"] == 800
    assert rows.iloc[0]["cash"] == pytest.approx(20_000 - rows.iloc[0]["cumulative_cost"], abs=1.0)


def test_month_end_is_judged_from_the_next_stored_session():
    c = flat(70)
    jan_end = c.index[c.index.month == 1][-1]
    pos = c.index.get_loc(jan_end)
    assert el.is_month_end(c, pos) and not el.is_month_end(c, pos - 1)
    assert not el.is_month_end(c, len(c) - 1)  # the newest session cannot be judged yet


def test_a_missing_or_repeated_close_blocks_the_run():
    c = flat(30)
    c.iloc[7, 1] = np.nan
    with pytest.raises(el.Blocked, match="missing"):
        el.run_ledger("idea1", c, str(c.index[2].date()))
    dup = pd.concat([flat(5), flat(5)])
    with pytest.raises(el.Blocked, match="twice"):
        el.validate(dup)


def test_a_late_start_after_a_gap_in_the_data_is_not_filled_forward():
    c = flat(30).drop(flat(30).index[12])
    assert len(el.validate(c)) == 29  # a missing session is simply not there: no row is invented
    assert el.run_ledger("hold_5050", c, str(c.index[3].date())).rows["session"].is_unique


def test_the_buys_are_scaled_down_when_costs_would_overspend_the_cash():
    book = el.Book(cash=100_000.0)
    prices = {N: 100.0, G: 50.0}
    el.trade(book, {N: 60_000.0, G: 60_000.0}, prices, el.COSTS_V1)  # asks for more than the cash
    assert book.cash >= 0
    assert book.shares[N] * 100.0 + book.shares[G] * 50.0 <= 100_000.0
    assert book.shares[N] > 0 and book.shares[G] > 0


@pytest.mark.parametrize("seed", [1, 4])
def test_idea1_chooses_what_the_tested_dual_momentum_rule_chooses(seed):
    c = closes(seed=seed)
    bars = {
        "equity": pd.DataFrame({"Close": c[N], "Open": c[N]}),
        "gold": pd.DataFrame({"Close": c[G], "Open": c[G]}),
    }
    held = u.held_dual_momentum(bars, el.MOMENTUM_DAYS, "best")
    led = el.run_ledger("idea1", c, str(c.index[0].date()))
    checked = 0
    book = el.Book()
    for i in range(el.MOMENTUM_DAYS + 2, len(c) - 1):
        if not el.is_month_end(c, i - 1):
            continue
        want = el.targets("idea1", c, i - 1, book, last=False)
        assert want is not None
        for key, col in ((N, "equity"), (G, "gold")):
            assert (want[key] > 0) == (held[col].iloc[i] > 0), c.index[i]
        checked += 1
    assert checked >= 5 and not led.rows.empty


def test_idea2_holds_what_the_tested_trend_rule_holds():
    c = closes(days=500, seed=6)
    bars = {"equity": pd.DataFrame({"Close": c[N], "Open": c[N]})}
    held = u.held_trend(bars, el.TREND_DAYS)
    book = el.Book()
    for i in range(el.TREND_DAYS + 3, len(c) - 1):
        want = el.targets("idea2", c, i - 1, book, last=False)
        assert (want[N] > 0) == (held["equity"].iloc[i] > 0), c.index[i]


def test_band_rebalance_acts_only_outside_forty_to_sixty_at_a_month_end():
    c = flat(70)
    jan_end_pos = c.index.get_loc(c.index[c.index.month == 1][-1])
    book = el.Book(cash=20_000.0, shares={N: 400, G: 800})
    assert el.targets("idea3", c, jan_end_pos, book, last=False) is None  # 50/50, inside the band
    book.shares = {N: 900, G: 100}  # equity 90,000 of 95,000: far outside
    want = el.targets("idea3", c, jan_end_pos, book, last=False)
    assert want[N] == want[G] == pytest.approx(min(90_000 + 5_000, el.IDEA1_CAP) / 2)
    assert el.targets("idea3", c, jan_end_pos - 1, book, last=False) is None  # not a month end


def test_running_twice_gives_identical_rows_and_the_double_cost_variant_is_sized_on_its_own():
    c = closes(days=400, seed=8)
    start = str(c.index[260].date())
    a = el.run_all(c, start)
    b = el.run_all(c, start)
    for key in a:
        pd.testing.assert_frame_equal(a[key].rows, b[key].rows)
    base, double = a["hold_5050:base"].rows.iloc[-1], a["hold_5050:double"].rows.iloc[-1]
    assert double["cumulative_cost"] > 1.9 * base["cumulative_cost"]
    assert double["nav"] < base["nav"]
    assert len({k.split(":")[0] for k in a}) == len(el.all_rules()) + len(el.BENCHMARKS)


def test_exposure_matched_weights_are_the_mean_of_the_replay_weights():
    c = closes(days=500, seed=2)
    replay = el.run_ledger("idea2", c, str(c.index[0].date())).rows
    weights = el.average_weights(replay)
    assert 0.0 <= weights[N] <= 0.4 and 0.0 <= weights[G] <= 0.4
    held = el.run_ledger("idea2", c, str(c.index[150].date()), matched=weights).rows
    assert held["ledger_id"].iloc[0] == "hold_matched_idea2"
    assert held["nifty_shares"].nunique() == 1  # bought once, never rebalanced


def test_idea3_never_lets_the_invested_part_stay_above_its_cap_after_a_month_end():
    idx = pd.bdate_range("2022-01-03", periods=700)
    rising = pd.DataFrame(
        {N: 100 * 1.003 ** np.arange(700), G: 50 * 1.003 ** np.arange(700)}, index=idx
    )
    rows = el.run_ledger("idea3", rising, str(idx[100].date())).rows.set_index("session")
    invested = rows["nifty_shares"] * rows["nifty_close"] + rows["gold_shares"] * rows["gold_close"]
    month_ends = [
        d for d, nxt in zip(rows.index[:-1], rows.index[1:], strict=True) if nxt.month != d.month
    ]
    after = invested.loc[[rows.index[rows.index.get_loc(d) + 1] for d in month_ends]]
    assert (after <= el.IDEA1_CAP * (el.TRIM_TOLERANCE + 0.01)).all()


def _first_sessions_of_months(rows):
    sessions = list(rows["session"])
    return {d for prev, d in zip(sessions[:-1], sessions[1:], strict=True) if d.month != prev.month}


@pytest.mark.parametrize(
    ("idea", "cap", "days"), [("idea1", el.IDEA1_CAP, 600), ("idea2", el.SLEEVE, 400)]
)
def test_a_held_position_is_traded_only_to_open_it_or_trim_it_to_its_cap_at_a_month_end(
    idea, cap, days
):
    idx = pd.bdate_range("2022-01-03", periods=days)
    rising = pd.DataFrame(
        {N: 100 * 1.003 ** np.arange(days), G: 50.0 + 0 * np.arange(days)}, index=idx
    )
    rows = el.run_ledger(idea, rising, str(idx[int(days * 0.5)].date())).rows
    trades = rows[(rows["buy_notional"] > 0) | (rows["sell_notional"] > 0)]
    later = trades.iloc[1:]
    assert len(later) > 0 and set(later["session"]) <= _first_sessions_of_months(rows)
    assert (later["buy_notional"] == 0).all()  # a trim sells, it never buys more
    for session in later["session"]:
        row = rows[rows["session"] == session].iloc[0]
        assert row["nifty_shares"] * row["nifty_close"] <= cap * 1.02, (idea, session)


def test_a_signal_that_never_changes_and_never_outgrows_the_cap_means_one_purchase():
    idx = pd.bdate_range("2023-01-02", periods=400)
    slow = pd.DataFrame({N: 100 + np.arange(400) * 0.01, G: 50 + np.arange(400) * 0.005}, index=idx)
    rows = el.run_ledger("idea2", slow, str(idx[150].date())).rows
    trades = rows[(rows["buy_notional"] > 0) | (rows["sell_notional"] > 0)]
    assert len(trades) == 1
