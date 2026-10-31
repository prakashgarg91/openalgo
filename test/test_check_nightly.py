"""Nightly capture checks on plain data (no broker, no database, no files)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "algo_backtest"))
import check_nightly as cn  # noqa: E402

THURSDAY = date(2026, 10, 29)
SATURDAY = date(2026, 10, 31)
WEDNESDAY = date(2026, 11, 4)


def option_symbols(count=62):
    """Weekly Nifty option symbols, CE and PE alternating down a strike ladder."""
    return [
        f"NIFTY26NOV26{24500 + 50 * (i // 2)}{'CE' if i % 2 == 0 else 'PE'}" for i in range(count)
    ]


def catalog(symbols):
    """Historify data-catalog rows for the option contracts plus the index, VIX and ETFs."""
    rows = []
    for symbol, exchange, interval in [
        *[(s, "NFO", "1m") for s in symbols],
        ("NIFTY", "NSE_INDEX", "1m"),
        ("INDIAVIX", "NSE_INDEX", "D"),
        ("NIFTYBEES", "NSE", "D"),
        ("GOLDBEES", "NSE", "D"),
    ]:
        rows.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "interval": interval,
                "first_timestamp": 0,
                "last_timestamp": 0,
                "record_count": 375,
                "last_download_at": 0,
            }
        )
    return rows


FIX_SHADOW = "Run run_forward_shadow.py tonight"
FIX_LEDGER = "Run run_etf_ledgers.py tonight"


def artifact(name, exists=True, age_hours=4.0):
    """One nightly-report entry the way main() reports it to check_day."""
    fix = FIX_SHADOW if "report" in name else FIX_LEDGER
    return {"name": name, "exists": exists, "age_hours": age_hours, "fix": fix}


def good_counts(**over):
    """Counts for a day where every check passes, with any key overridden to break one check."""
    counts = {
        "option_candles": dict.fromkeys(option_symbols(), 375),
        "index_candles": 375,
        "vix_days": ["2026-10-28", "2026-10-29"],
        "etf_days": {
            "NIFTYBEES": ["2026-10-28", "2026-10-29"],
            "GOLDBEES": ["2026-10-28", "2026-10-29"],
        },
        "before_close": False,
        "artifacts": [artifact("db/forward_shadow/report.json"), artifact("db/etf_ledger")],
    }
    counts.update(over)
    return counts


def problems(findings):
    return [message for level, message in findings if level == cn.PROBLEM]


def test_a_good_day_reports_everything_ok():
    findings = cn.check_day(THURSDAY, catalog(option_symbols()), good_counts())
    assert findings
    assert all(level == cn.OK for level, _ in findings)


def test_sixty_full_contracts_is_enough_but_fifty_nine_is_a_problem():
    rows = catalog(option_symbols())
    enough = good_counts(option_candles=dict.fromkeys(option_symbols(60), 375))
    assert not problems(cn.check_day(THURSDAY, rows, enough))

    short = good_counts(option_candles=dict.fromkeys(option_symbols(59), 375))
    found = cn.check_day(THURSDAY, rows, short)
    assert len(problems(found)) == 1
    message = problems(found)[0]
    assert "59" in message and "capture_option_candles.py" in message


def test_a_part_day_contract_is_not_counted_as_full():
    symbols = option_symbols(60) + ["NIFTY26NOV2626100PE"]
    saved = dict.fromkeys(symbols, 375)
    saved["NIFTY26NOV2626100PE"] = 299  # the capture stopped after 299 candles on this one
    assert not problems(cn.check_day(THURSDAY, catalog(symbols), good_counts(option_candles=saved)))


def test_contracts_that_stopped_early_are_named():
    symbols = option_symbols(59) + ["NIFTY26NOV2626100PE"]
    saved = dict.fromkeys(symbols, 375)
    saved["NIFTY26NOV2626100PE"] = 299
    found = cn.check_day(THURSDAY, catalog(symbols), good_counts(option_candles=saved))
    assert len(problems(found)) == 1
    assert "NIFTY26NOV2626100PE" in problems(found)[0]


def test_the_index_needs_a_full_session_of_candles():
    enough = cn.check_day(THURSDAY, catalog(option_symbols()), good_counts(index_candles=370))
    assert not problems(enough)

    found = cn.check_day(THURSDAY, catalog(option_symbols()), good_counts(index_candles=369))
    assert len(problems(found)) == 1
    message = problems(found)[0]
    assert "Nifty index" in message and "capture_option_candles.py" in message


def test_india_vix_needs_a_recent_close_for_the_previous_session():
    # A Friday close still counts as the previous session after a long weekend
    enough = cn.check_day(THURSDAY, catalog(option_symbols()), good_counts(vix_days=["2026-10-22"]))
    assert not problems(enough)

    found = cn.check_day(THURSDAY, catalog(option_symbols()), good_counts(vix_days=["2026-10-20"]))
    assert len(problems(found)) == 1
    message = problems(found)[0]
    assert "India VIX" in message and "capture_option_candles.py" in message


def test_a_day_with_no_vix_history_at_all_is_a_problem():
    found = cn.check_day(THURSDAY, catalog(option_symbols()), good_counts(vix_days=[]))
    assert len(problems(found)) == 1
    assert "India VIX" in problems(found)[0]


def test_an_etf_close_for_the_day_is_needed_after_the_close():
    counts = good_counts(
        etf_days={"NIFTYBEES": ["2026-10-28"], "GOLDBEES": ["2026-10-28", "2026-10-29"]}
    )
    found = cn.check_day(THURSDAY, catalog(option_symbols()), counts)
    assert len(problems(found)) == 1
    assert "NIFTYBEES" in problems(found)[0]

    counts = good_counts(
        etf_days={"NIFTYBEES": ["2026-10-29"], "GOLDBEES": ["2026-10-28", "2026-10-29"]}
    )
    assert not problems(cn.check_day(THURSDAY, catalog(option_symbols()), counts))


def test_before_the_close_the_previous_session_close_is_accepted():
    counts = good_counts(
        etf_days={"NIFTYBEES": ["2026-10-28"], "GOLDBEES": ["2026-10-28"]},
        before_close=True,
    )
    assert not problems(cn.check_day(THURSDAY, catalog(option_symbols()), counts))

    counts = good_counts(etf_days={"NIFTYBEES": [], "GOLDBEES": []}, before_close=True)
    found = cn.check_day(THURSDAY, catalog(option_symbols()), counts)
    assert len(problems(found)) == 2


def test_a_missing_nightly_report_is_a_problem():
    counts = good_counts(
        artifacts=[
            artifact("db/forward_shadow/report.json", exists=False),
            artifact("db/etf_ledger"),
        ]
    )
    found = cn.check_day(THURSDAY, catalog(option_symbols()), counts)
    assert len(problems(found)) == 1
    message = problems(found)[0]
    assert "report.json" in message and "run_forward_shadow.py" in message


def test_a_stale_nightly_report_is_a_problem():
    counts = good_counts(
        artifacts=[
            artifact("db/forward_shadow/report.json", age_hours=36.0),  # 36 hours is still fresh
            artifact("db/etf_ledger", age_hours=40.0),
        ]
    )
    found = cn.check_day(THURSDAY, catalog(option_symbols()), counts)
    assert len(problems(found)) == 1
    message = problems(found)[0]
    assert "etf_ledger" in message and "run_etf_ledgers.py" in message


def test_a_weekend_with_no_candles_is_not_a_problem():
    found = cn.check_day(
        SATURDAY, catalog(option_symbols()), good_counts(index_candles=0, option_candles={})
    )
    assert len(found) == 1 and found[0][0] == cn.OK
    assert "no trading" in found[0][1]


def test_a_weekend_special_session_is_checked_like_any_day():
    counts = good_counts(
        vix_days=["2026-10-30", "2026-10-31"],
        etf_days={"NIFTYBEES": ["2026-10-31"], "GOLDBEES": ["2026-10-31"]},
    )
    assert not problems(cn.check_day(SATURDAY, catalog(option_symbols()), counts))


def test_a_weekday_holiday_is_not_waved_off():
    counts = good_counts(
        index_candles=0,
        option_candles={},
        vix_days=["2026-10-30"],
        etf_days={"NIFTYBEES": ["2026-10-30"], "GOLDBEES": ["2026-10-30"]},
    )
    found = cn.check_day(WEDNESDAY, catalog(option_symbols()), counts)
    assert any(level == cn.PROBLEM for level, _ in found)
    assert any("Nifty index" in message for message in problems(found))


def test_an_empty_store_is_one_problem():
    found = cn.check_day(THURSDAY, [], good_counts(index_candles=0, option_candles={}))
    assert len(found) == 1
    assert found[0][0] == cn.PROBLEM and "capture_option_candles.py" in found[0][1]


def test_only_nifty_options_count_toward_the_sixty():
    symbols = option_symbols(59) + ["NIFTY26DEC31245120.5CE"]
    saved = dict.fromkeys(symbols, 375)
    assert not problems(cn.check_day(THURSDAY, catalog(symbols), good_counts(option_candles=saved)))

    symbols = option_symbols(59) + ["BANKNIFTY26NOV2648000CE"]
    saved = dict.fromkeys(symbols, 375)
    found = cn.check_day(THURSDAY, catalog(symbols), good_counts(option_candles=saved))
    assert len(problems(found)) == 1  # a Bank Nifty option does not fill the Nifty quota
