"""The account recorder turns the app's read replies into one summary row."""

from datetime import datetime

from scripts.algo_backtest import record_account as ra


def test_summary_adds_realized_and_unrealized_and_counts_open_positions():
    row = ra.summarise(
        datetime(2026, 11, 17, 15, 40),
        "sandbox",
        {
            "data": {
                "availablecash": "89,760.90",
                "utiliseddebits": "9789.00",
                "m2mrealized": "100",
                "m2munrealized": "2492.75",
            }
        },
        {"data": [{"quantity": "-65"}, {"quantity": "65"}, {"quantity": "0"}]},
        {"data": [{}, {}]},
        {"data": {"orders": [{}, {}, {}]}},
    )
    assert row["total_pnl"] == 2592.75 and row["available_cash"] == 89760.9
    assert row["open_positions"] == 2 and row["trades_today"] == 2 and row["orders_today"] == 3


def test_a_missing_reply_gives_zeros_not_a_crash():
    row = ra.summarise(datetime(2026, 11, 17), "sandbox", {}, {}, {}, {})
    assert row["total_pnl"] == 0 and row["open_positions"] == 0
