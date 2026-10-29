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


def test_paced_spaces_requests_and_retries_once_after_a_rate_limit():
    now = [0.0]
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    calls = []

    def history(*args):
        calls.append(args)
        if len(calls) == 2:
            raise RuntimeError("HTTP 429 Too Many Requests")
        return pd.DataFrame({"x": [1]})

    fetch = oc.paced(history, per_second=2, pause=60, sleep=sleep, clock=lambda: now[0])
    fetch("a")
    fetch("b")
    assert len(calls) == 3  # the rate-limited call was tried a second time
    assert 60 in waits
    assert all(w <= 60 for w in waits)
    assert 0.5 in waits  # the second request waited half a second for the 2 per second cap


def test_paced_raises_other_errors_unchanged():
    def history(*args):
        raise ValueError("bad symbol")

    fetch = oc.paced(history, sleep=lambda s: None, clock=lambda: 0.0)
    try:
        fetch("a")
    except ValueError as exc:
        assert "bad symbol" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_capture_context_stores_the_index_and_vix_and_survives_a_failure():
    stored = []
    frame = pd.DataFrame(
        {"timestamp": [1], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}
    )
    asked = []

    def history(symbol, exchange, interval, start, end):
        asked.append((symbol, exchange, interval, start, end))
        if symbol == "INDIAVIX":
            raise RuntimeError("feed down")
        return frame

    def store(frame_, symbol, exchange, interval):
        stored.append((symbol, exchange, interval))
        return len(frame_)

    result = oc.capture_context("2026-10-29", history, store)
    assert stored == [("NIFTY", "NSE_INDEX", "1m")]
    assert result == {"index_candles": 1, "vix_days": 0, "failed": 1}
    index_call = asked[0]
    assert index_call[3] < "2026-10-29" and index_call[4] == "2026-10-29"


def test_a_wide_day_keeps_the_far_leg_of_a_spread_opened_before_the_move():
    data = rows(range(23000, 27000, 50))
    close = 25000.0
    plain = {c["strike"] for c in oc.select_contracts(data, close, EXPIRY)}
    assert max(plain) == 25800
    # Nifty was 24,500 at 10:15 and rallied 500: a put spread sold at 24,500 holds 24,100.
    wide = {c["strike"] for c in oc.select_contracts(data, close, EXPIRY, ((24450.0, 25020.0),))}
    assert min(wide) == 23950 and 24100 in wide
    assert max(wide) == 25800  # never narrower than the plain band


def test_the_previous_session_range_keeps_the_strikes_of_an_overnight_position():
    data = rows(range(22000, 27000, 50))
    ranges = {"2026-10-28": (24400.0, 24800.0), "2026-10-29": (25600.0, 26000.0)}
    reach = oc.reach_for(ranges, "2026-10-29")
    assert len(reach) == 2
    strikes = {c["strike"] for c in oc.select_contracts(data, 25900.0, EXPIRY, reach)}
    assert 23900 in strikes  # long leg of a put spread sold at 24,300 the evening before


def test_index_ranges_groups_candles_by_india_session():
    # 2026-10-29 09:15 IST is 03:45 UTC
    base = int(pd.Timestamp("2026-10-29 03:45", tz="UTC").timestamp())
    f = pd.DataFrame(
        {
            "timestamp": [base, base + 60, base - 86400],
            "high": [101.0, 105.0, 90.0],
            "low": [99.0, 98.0, 80.0],
            "close": [100.0, 100.0, 85.0],
        }
    )
    got = oc.index_ranges(lambda *a: f, "2026-10-29")
    assert got == {"2026-10-28": (80.0, 90.0), "2026-10-29": (98.0, 105.0)}
    assert oc.index_ranges(lambda *a: pd.DataFrame(), "2026-10-29") == {}


def test_an_empty_context_answer_counts_as_a_failure_not_a_quiet_day():
    stored = []
    result = oc.capture_context(
        "2026-10-29", lambda *a: pd.DataFrame(), lambda *a: stored.append(a) or 0
    )
    assert stored == []
    assert result == {"index_candles": 0, "vix_days": 0, "failed": 2}
