"""Bid and ask snapshot rows and the spread summary, on made-up quotes."""

import pandas as pd

from services import bidask_snapshot as bs

CONTRACTS = [
    {
        "symbol": "NIFTY03NOV2625000CE",
        "expiry": "03-NOV-26",
        "strike": 25000,
        "instrumenttype": "CE",
    },
    {
        "symbol": "NIFTY03NOV2625400CE",
        "expiry": "03-NOV-26",
        "strike": 25400,
        "instrumenttype": "CE",
    },
    {
        "symbol": "NIFTY03NOV2624600PE",
        "expiry": "03-NOV-26",
        "strike": 24600,
        "instrumenttype": "PE",
    },
]


def quote(symbol, bid, ask, ltp=1.0):
    return {
        "symbol": symbol,
        "exchange": "NFO",
        "data": {"bid": bid, "ask": ask, "ltp": ltp, "volume": 5, "oi": 9},
    }


def rows():
    quotes = [
        quote("NIFTY03NOV2625000CE", 100.0, 100.2),
        quote("NIFTY03NOV2625400CE", 10.0, 0.0),  # no ask
        {"symbol": "NIFTY03NOV2624600PE", "exchange": "NFO", "error": "No quote data available"},
        quote("UNKNOWN", 1.0, 2.0),
    ]
    return bs.build_rows(quotes, CONTRACTS, 25010.0, "2026-11-02 10:15:00", "1015", "03-NOV-26")


def test_a_two_sided_quote_gets_its_spread_and_distance():
    r = rows()
    assert len(r) == 2  # the error and the unknown symbol are left out
    first = r[0]
    assert abs(first["spread"] - 0.2) < 1e-9 and abs(first["mid"] - 100.1) < 1e-9
    assert first["distance"] == -10.0 and first["kind"] == "CE"
    assert abs(first["spread_pct"] - 0.2 / 100.1) < 1e-12


def test_a_missing_side_keeps_the_row_with_an_empty_spread():
    second = rows()[1]
    assert second["ask"] is None and second["spread"] is None and second["spread_pct"] is None


def test_the_summary_groups_by_moment_kind_and_distance():
    f = pd.DataFrame(rows(), columns=bs.COLUMNS)
    s = bs.summarize(f)
    near = s[(s["bucket"] == "within 100")].iloc[0]
    assert (
        near["quotes"] == 1
        and abs(near["median_spread"] - 0.2) < 1e-9
        and near["two_sided_share"] == 1.0
    )
    far = s[(s["bucket"] == "300 to 500")].iloc[0]
    assert far["two_sided_share"] == 0.0
