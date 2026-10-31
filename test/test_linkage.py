"""Linkage study building blocks: timing safety, the robust slope test, selection and shuffling."""

import numpy as np
import pandas as pd

from services.algos import linkage as lk


def test_a_us_close_of_the_previous_evening_is_usable_but_the_same_day_asian_bar_is_not():
    opens = pd.DatetimeIndex(["2026-10-29 03:45"], tz="UTC")  # Nifty open
    us = pd.Series(
        [0.01, 0.02], index=pd.DatetimeIndex(["2026-10-27 13:30", "2026-10-28 13:30"], tz="UTC")
    )
    got = lk.known_before(us, us.index, 9, opens)
    assert got.iloc[0] == 0.02  # the 28th US session ended the evening before
    asia = pd.Series(
        [0.5, 0.9], index=pd.DatetimeIndex(["2026-10-28 00:00", "2026-10-29 00:00"], tz="UTC")
    )
    got = lk.known_before(asia, asia.index, 9, opens)
    assert got.iloc[0] == 0.5  # the 29th Asian session ends at 09:00 UTC, after the Indian open


def test_a_currency_bar_that_ends_after_the_open_is_not_used():
    opens = pd.DatetimeIndex(["2026-10-29 03:45"], tz="UTC")
    fx = pd.Series(
        [1.0, 2.0], index=pd.DatetimeIndex(["2026-10-27 23:00", "2026-10-28 23:00"], tz="UTC")
    )
    assert (
        lk.known_before(fx, fx.index, 24, opens).iloc[0] == 1.0
    )  # the second ends at 23:00 on the 29th


def test_slope_test_finds_a_real_link_and_not_a_fake_one():
    rng = np.random.default_rng(1)
    x = rng.normal(size=3000)
    y = 0.3 * x + rng.normal(size=3000)
    slope, t, n = lk.ols_hac(x, y)
    assert n == 3000 and 0.2 < slope < 0.4 and abs(t) > 8
    _, t_noise, _ = lk.ols_hac(x, rng.normal(size=3000))
    assert abs(t_noise) < 4


def test_benjamini_hochberg_keeps_the_small_p_values_only():
    p = np.array([0.0001, 0.0004, 0.2, 0.5, np.nan, 0.9])
    assert list(lk.benjamini_hochberg(p, 0.05)) == [True, True, False, False, False, False]


def test_block_shuffle_keeps_every_value_and_keeps_blocks_whole():
    v = np.arange(100.0)
    out = lk.block_shuffle(v, np.random.default_rng(0), 20)
    assert sorted(out) == list(v)
    for i in range(0, 100, 20):
        chunk = out[i : i + 20]
        assert list(chunk) == list(np.arange(chunk[0], chunk[0] + 20))


def test_ridge_recovers_a_signal_and_the_penalty_grid_runs():
    rng = np.random.default_rng(2)
    x = rng.normal(size=(600, 5))
    y = 2 * x[:, 0] + rng.normal(size=600)
    alpha = lk.choose_alpha(x, y)
    coef = lk.ridge_fit(x, y, alpha)
    assert coef[0] > 1.5 and abs(coef[1]) < 0.3
