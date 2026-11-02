import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "algo_backtest"))
import day_complete as dc  # noqa: E402

DAY = date(2026, 11, 2)
GOOD = """==== 02-11-2026 16:00:00.10
{'contracts': 68, 'stored': 68, 'candles': 26068, 'no_data': 0, 'failed': 0}
{'index_candles': 2250, 'vix_days': 32, 'etf_days': 570, 'failed': 0}
ETF ledgers 2026-10-29-v1 (SHADOW)
Everything the forward tests need from this day is in place.
Snapshot written: historify-20261102.duckdb (3.9 MB); removed 0 old.
"""
ALL = {"1015", "1430", "1500"}


def test_a_complete_day_has_no_problems():
    assert dc.judge("==== 30-10-2026 16:00:00.10\nold\n" + GOOD, DAY, ALL) == []


def test_only_the_last_run_of_the_day_counts():
    bad = GOOD.replace(
        "'candles': 26068, 'no_data': 0, 'failed': 0", "'candles': 0, 'no_data': 0, 'failed': 3"
    )
    assert dc.judge(bad + GOOD, DAY, ALL) == []
    assert dc.judge(GOOD + bad, DAY, ALL) != []


def test_no_run_today_blocks():
    assert dc.judge(GOOD.replace("02-11-2026", "30-10-2026"), DAY, ALL)


def test_capture_failure_blocks():
    bad = GOOD.replace("'no_data': 0, 'failed': 0", "'no_data': 0, 'failed': 2")
    assert any("capture reported failures" in p for p in dc.judge(bad, DAY, ALL))


def test_context_failure_blocks():
    bad = GOOD.replace("'etf_days': 570, 'failed': 0", "'etf_days': 0, 'failed': 1")
    assert any("context reported failures" in p for p in dc.judge(bad, DAY, ALL))


def test_failed_nightly_check_blocks():
    bad = GOOD.replace(
        "Everything the forward tests need from this day is in place.\n", "PROBLEM\n"
    )
    assert any("nightly data check" in p for p in dc.judge(bad, DAY, ALL))


def test_missing_snapshot_or_label_blocks():
    assert dc.judge(GOOD.replace("historify-20261102", "historify-20261030"), DAY, ALL)
    assert any("1430" in p for p in dc.judge(GOOD, DAY, {"1015", "1500"}))
