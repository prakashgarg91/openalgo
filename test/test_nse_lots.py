"""The Nifty lot by expiry follows the circulars and never guesses outside them."""

import pandas as pd
import pytest

from services.algos import intraday, nse_lots


@pytest.mark.parametrize(
    "expiry,lot",
    [
        ("2021-04-29", 75),  # existing contracts at the 31 Mar 2021 circular
        ("2021-07-22", 75),  # last July weekly before the revised monthly
        ("2021-07-29", 50),  # first expiry with the revised lot
        ("2021-08-05", 50),
        ("2024-04-25", 50),  # last monthly with 50 (NSE/FAOP/61415)
        ("2024-05-02", 25),  # first weekly with 25
        ("2024-12-26", 25),
        ("2025-01-02", 75),
        ("2025-12-30", 75),
        ("2026-01-06", 65),
        ("2026-11-09", 65),
    ],
)
def test_lot_by_expiry(expiry, lot):
    assert nse_lots.nifty_lot(expiry) == lot


def test_an_expiry_before_the_first_documented_one_has_no_lot():
    assert nse_lots.nifty_lot("2021-03-25") is None
    assert nse_lots.nifty_lot("2015-09-24") is None


def test_every_row_cites_an_exchange_circular_and_starts_are_increasing():
    starts = [pd.Timestamp(s) for s, _, _ in nse_lots.NIFTY_LOTS]
    assert starts == sorted(starts)
    assert all("NSE/FAOP/" in source for _, _, source in nse_lots.NIFTY_LOTS)


def test_it_agrees_with_the_lot_the_replays_already_use_from_october_2024():
    for expiry in (
        "2024-10-03",
        "2024-12-26",
        "2025-01-02",
        "2025-12-30",
        "2026-01-06",
        "2026-10-27",
    ):
        assert nse_lots.nifty_lot(expiry) == intraday.lot_size_for_expiry(pd.Timestamp(expiry))


def test_the_replay_lot_function_uses_the_circular_table_before_october_2024():
    for expiry, lot in (
        ("2021-08-05", 50),
        ("2023-06-29", 50),
        ("2024-05-02", 25),
        ("2024-09-26", 25),
    ):
        assert intraday.lot_size_for_expiry(pd.Timestamp(expiry)) == lot
