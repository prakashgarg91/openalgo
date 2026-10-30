"""The twelve candidate ETF rules: each decision, the exposure cap, and that every ledger runs cleanly."""

import numpy as np
import pandas as pd
import pytest

from services.algos import etf_candidates as ec
from services.algos import etf_ledger as el
from services.algos import universe as u

N, G = el.NIFTY, el.GOLD


def frame(nifty, gold=None, start="2022-01-03"):
    n = len(nifty)
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame(
        {
            N: np.asarray(nifty, float),
            G: np.asarray(gold if gold is not None else np.full(n, 50.0), float),
        },
        index=idx,
    )


def random_closes(days=900, seed=3):
    idx = pd.bdate_range("2021-01-04", periods=days)
    out = {}
    for name, s in ((N, seed), (G, seed + 9)):
        r = np.random.default_rng(s).normal(0.0004, 0.01, days)
        out[name] = 100 * np.exp(np.cumsum(r))
    return pd.DataFrame(out, index=idx)


def test_there_are_twelve_candidates_with_distinct_names():
    assert len(ec.NAMES) == 12 and len(set(ec.NAMES)) == 12
    assert el.all_rules() == (*el.IDEAS, *ec.NAMES)


def test_trend200_wants_the_etf_only_above_its_average_and_matches_the_tested_trend_rule():
    c = random_closes(seed=5)
    bars = {"equity": pd.DataFrame({"Close": c[N], "Open": c[N]})}
    held = u.held_trend(bars, 200)
    book = el.Book()
    for i in range(205, len(c) - 1):
        want = ec.c01_trend200(c, i - 1, book, False)
        assert (want[N] > 0) == (held["equity"].iloc[i] > 0), c.index[i]


def test_cross_needs_the_fast_average_over_the_slow_one():
    falling_then_rising = np.r_[np.linspace(150, 90, 250), np.linspace(90, 160, 60)]
    c = frame(falling_then_rising)
    book = el.Book()
    assert ec.c02_cross50_200(c, 249, book, False)[N] == 0.0  # fast under slow in a long fall
    assert ec.c02_cross50_200(c, 309, book, False)[N] > 0  # after a strong rise the fast is over


def test_absolute_momentum_acts_only_at_a_month_end():
    c = frame(np.linspace(100, 200, 400))
    book = el.Book()
    assert ec.c03_absmom252(c, 300, book, False) is None
    assert ec.c03_absmom252(c, 300, book, True)[N] > 0
    assert ec.c03_absmom252(frame(np.linspace(200, 100, 400)), 300, book, True)[N] == 0.0


def test_donchian_enters_on_a_new_55_day_high_and_leaves_on_a_20_day_low():
    c = frame(np.r_[np.full(60, 100.0), [101.0]])  # a close above every close of the previous 55
    assert ec.c04_donchian55(c, 60, el.Book(), False)[N] > 0
    held = el.Book(shares={N: 100, G: 0})
    drop = frame(np.r_[np.full(60, 100.0), [99.0]])  # under the lowest of the previous 20
    assert ec.c04_donchian55(drop, 60, held, False)[N] == 0.0
    inside = frame(np.r_[np.full(60, 100.0), [100.0]])
    assert ec.c04_donchian55(inside, 60, held, False)[N] is None  # held, still inside: leave it


def test_rsi2_buys_a_dip_in_an_uptrend_and_not_a_dip_in_a_downtrend():
    up = np.r_[np.linspace(100, 200, 250), 196, 190, 183]
    assert ec.c05_rsi2_uptrend(frame(up), len(up) - 1, el.Book(), False)[N] > 0
    down = np.r_[np.linspace(200, 100, 250), 98, 95, 91]
    assert ec.c05_rsi2_uptrend(frame(down), len(down) - 1, el.Book(), False)[N] == 0.0


def test_gold_trend_uses_only_the_gold_etf():
    c = frame(np.full(150, 100.0), np.linspace(50, 80, 150))
    want = ec.c06_gold_trend100(c, 149, el.Book(), False)
    assert want[G] > 0 and want[N] == 0.0


def test_volatility_target_shrinks_the_position_when_volatility_is_high():
    calm = frame(100 * np.exp(np.cumsum(np.full(100, 0.0002))))
    wild = frame(100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.03, 100))))
    assert ec.c07_voltarget(calm, 99, el.Book(), True)[N] == pytest.approx(ec.CAP)  # calm: capped
    assert 0 < ec.c07_voltarget(wild, 99, el.Book(), True)[N] < ec.CAP * 0.6
    assert ec.c07_voltarget(calm, 99, el.Book(), False) is None


def test_drawdown_filter_leaves_after_ten_percent_and_returns_within_five():
    path = np.r_[np.linspace(100, 200, 260), np.linspace(200, 170, 30)]  # 15 percent off the high
    c = frame(path)
    held = el.Book(shares={N: 100, G: 0})
    assert ec.c08_drawdown_filter(c, len(path) - 1, held, False)[N] == 0.0
    out = el.Book()
    assert (
        ec.c08_drawdown_filter(c, len(path) - 1, out, False)[N] == 0.0
    )  # not back within 5 percent
    recovered = frame(np.r_[np.linspace(100, 200, 260), np.linspace(200, 195, 5)])
    assert ec.c08_drawdown_filter(recovered, len(recovered) - 1, out, False)[N] > 0


def test_both_sleeves_use_their_own_average():
    c = frame(np.linspace(100, 200, 250), np.linspace(80, 40, 250))  # equity rising, gold falling
    want = ec.c09_both_trend200(c, 249, el.Book(), False)
    assert want[N] == el.SLEEVE and want[G] == 0.0


def test_inverse_volatility_weights_favour_the_quieter_asset_and_sum_to_the_cap():
    rng = np.random.default_rng(2)
    wild = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 120)))
    calm = 50 * np.exp(np.cumsum(rng.normal(0, 0.004, 120)))
    want = ec.c10_inverse_vol(frame(wild, calm), 119, el.Book(), True)
    assert want[G] > want[N] and want[N] + want[G] == pytest.approx(ec.CAP)


def test_dual126_picks_the_stronger_rising_etf_and_cash_when_both_fall():
    c = frame(np.linspace(100, 150, 200), np.linspace(50, 90, 200))
    want = ec.c11_dual126(c, 199, el.Book(), True)
    assert want[G] > 0 and want[N] == 0.0
    both_down = frame(np.linspace(150, 100, 200), np.linspace(90, 50, 200))
    assert ec.c11_dual126(both_down, 199, el.Book(), True) == {N: 0.0, G: 0.0}


def test_risk_off_moves_to_gold_when_only_gold_is_trending_up():
    c = frame(np.linspace(200, 100, 260), np.linspace(50, 100, 260))
    want = ec.c12_risk_off_to_gold(c, 259, el.Book(), False)
    assert want[G] > 0 and want[N] == 0.0
    both_down = frame(np.linspace(200, 100, 260), np.linspace(100, 50, 260))
    assert ec.c12_risk_off_to_gold(both_down, 259, el.Book(), False) == {N: 0.0, G: 0.0}


@pytest.mark.parametrize("name", ec.NAMES)
def test_every_candidate_runs_keeps_cash_non_negative_and_stays_near_its_cap(name):
    c = random_closes(days=900, seed=7)
    rows = el.run_ledger(name, c, str(c.index[400].date())).rows
    assert not rows.empty and (rows["cash"] >= 0).all()
    invested = rows["nifty_shares"] * rows["nifty_close"] + rows["gold_shares"] * rows["gold_close"]
    assert invested.max() <= ec.CAP * 1.4  # month-end trims keep growth between them bounded
    again = el.run_ledger(name, c, str(c.index[400].date())).rows
    pd.testing.assert_frame_equal(rows, again)


def test_run_all_contains_every_rule_in_both_cost_variants():
    c = random_closes(days=700, seed=4)
    ledgers = el.run_all(c, str(c.index[300].date()))
    for name in (*el.all_rules(), *el.BENCHMARKS):
        assert f"{name}:base" in ledgers and f"{name}:double" in ledgers
