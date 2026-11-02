"""The Nifty lot size follows the contract's expiry, not a single date or a fixed 75.

Source: Upstox's expired-contract listing, read on 2 November 2026 (lot_size per expiry): 25 for expiries up
to 26 December 2024, 75 from 2 January 2025 to 30 December 2025, 65 from 6 January 2026.
"""

import pandas as pd
import pytest

from services.algos import intraday, lab


@pytest.mark.parametrize(
    ("expiry", "lot"),
    [
        ("2024-10-03", 25),
        ("2024-11-28", 25),
        ("2024-12-26", 25),
        ("2025-01-02", 75),
        ("2025-06-26", 75),
        ("2025-12-30", 75),
        ("2026-01-06", 65),
        ("2026-10-27", 65),
        ("2026-11-09", 65),
    ],
)
def test_the_lot_follows_the_contracts_expiry(expiry, lot):
    assert intraday.lot_size_for_expiry(pd.Timestamp(expiry)) == lot


def test_the_charges_scale_with_the_lot_instead_of_a_fixed_75():
    entry, exit_ = [100.0, 20.0], [60.0, 10.0]
    sells = [True, False]
    default = lab.trade_cost(lab.CONSERVATIVE, entry, exit_, sells)
    assert default == lab.trade_cost(lab.CONSERVATIVE, entry, exit_, sells, lot_size=75)
    small = lab.trade_cost(lab.CONSERVATIVE, entry, exit_, sells, lot_size=25)
    assert 0 < small < default


def test_a_trade_record_uses_the_expiry_lot_for_both_the_result_and_the_charges():
    expiry = pd.Timestamp("2024-10-03")
    ts0 = expiry - pd.Timedelta(days=2) + pd.Timedelta(hours=10, minutes=15)
    walk = intraday.Walk(ts0 + pd.Timedelta(hours=1), 70.0, "time", 90.0, 20.0)
    record = intraday._trade_record(
        ts0, "CE", expiry, 25000.0, 25100.0, (100.0, 20.0), walk, lab.CONSERVATIVE
    )
    assert record["net"] == pytest.approx(record["pts"] * 25 - record["cost"])
    again = intraday._trade_record(
        ts0 + pd.Timedelta(days=800),
        "CE",
        pd.Timestamp("2026-10-27"),
        25000.0,
        25100.0,
        (100.0, 20.0),
        walk,
        lab.CONSERVATIVE,
    )
    assert again["net"] == pytest.approx(again["pts"] * 65 - again["cost"])
    assert again["cost"] > record["cost"]  # a larger lot pays more in charges
