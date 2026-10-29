"""Nightly option candle capture: contract choice and the capture loop (no broker, no database)."""

from datetime import datetime

import pandas as pd

from services import option_capture as oc

EXPIRY = "04-NOV-25"


def rows(strikes, expiry=EXPIRY):
    return [
        {
            "symbol": f"NIFTY{expiry}{int(k)}{kind}",
            "expiry": expiry,
            "strike": k,
            "instrumenttype": kind,
        }
        for k in strikes
        for kind in ("CE", "PE")
    ]


def test_nearest_expiry_skips_past_dates_and_keeps_today():
    expiries = ["28-Oct-25", "04-Nov-25", "11-Nov-25"]
    assert oc.nearest_expiry(expiries, datetime(2025, 10, 29)) == "04-Nov-25"
    assert oc.nearest_expiry(expiries, datetime(2025, 11, 4)) == "04-Nov-25"
    assert oc.nearest_expiry(expiries, datetime(2025, 11, 12)) is None


def test_select_contracts_keeps_a_band_around_the_money_for_one_expiry():
    data = rows(range(23000, 27000, 50)) + rows([25000], expiry="11-NOV-25")
    chosen = oc.select_contracts(data, 25012.0, EXPIRY)
    strikes = {c["strike"] for c in chosen}
    assert min(strikes) == 24200 and max(strikes) == 25800
    assert {c["expiry"] for c in chosen} == {EXPIRY}
    assert len(chosen) == 2 * len(strikes)


def frame():
    return pd.DataFrame(
        {
            "timestamp": [1, 2],
            "open": [1, 1],
            "high": [2, 2],
            "low": [1, 1],
            "close": [2, 2],
            "volume": [5, 5],
            "oi": [9, 9],
        }
    )


def test_capture_counts_stored_empty_and_failed_and_never_stops():
    contracts = rows([25000, 25050])

    def history(symbol, exchange, interval, start, end):
        if symbol.endswith("25000CE"):
            raise RuntimeError("broker down")
        if symbol.endswith("25000PE"):
            return pd.DataFrame()
        return frame()

    saved = []

    def store(df, symbol, exchange, interval):
        saved.append((symbol, exchange, interval))
        return len(df)

    result = oc.capture(contracts, "2025-10-29", history, store)
    assert result == {"contracts": 4, "stored": 2, "candles": 4, "no_data": 1, "failed": 1}
    assert all(e == "NFO" and i == "1m" for _, e, i in saved)


def test_spot_is_the_last_close_or_none():
    f = frame().assign(close=[10.0, 20.0])
    assert oc.spot_from_index(lambda *a: f, "2025-10-29") == 20.0
    assert oc.spot_from_index(lambda *a: pd.DataFrame(), "2025-10-29") is None
