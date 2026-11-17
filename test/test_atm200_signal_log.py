"""Tests for scripts/algo_backtest/atm200_signal_log.py: the exploratory ATM 200 signal log.

Synthetic snapshot files only, written under tmp_path. No network, no clock, no broker.
This is a log, not a registered test: the file is here to keep the logic honest.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.algo_backtest import atm200_signal_log as sl  # noqa: E402
from services.algos import atm200_rule as rule  # noqa: E402

HEADER = "stamp,label,expiry,symbol,kind,strike,spot,distance,bid,ask,mid,spread,spread_pct,ltp,volume,oi"
VIX_HEADER = "timestamp_utc,open,high,low,close,volume,adjclose"
EXPIRY = "03-NOV-26"
SPOT = 25200.0  # ATM 25200, so the sold call is 25200 and the bought call is 25400
TIMES = {"1015": "10:16:00", "1430": "14:30:00", "1500": "15:00:00"}


def _call_rows(
    day: str, label: str, sold_bid, sold_ask, bought_bid, bought_ask, expiry: str
) -> list[str]:
    stamp = f"{day} {TIMES[label]}"
    rows = []
    for strike, kind, bid, ask in (
        (25200, "CE", sold_bid, sold_ask),
        (25400, "CE", bought_bid, bought_ask),
        (25200, "PE", 5, 6),
    ):
        rows.append(
            f"{stamp},{label},{expiry},NIFTY{expiry}{strike}{kind},{kind},{strike},{SPOT},0,"
            f"{bid},{ask},0,0,0,0,0,0"
        )
    return rows


def _write_day(repo: Path, day: str, marks: dict[str, tuple], expiry: str = EXPIRY) -> None:
    """marks maps a label to (sold_bid, sold_ask, bought_bid, bought_ask)."""
    folder = repo / "bidask"
    folder.mkdir(parents=True, exist_ok=True)
    lines = [HEADER]
    for label, prices in marks.items():
        lines += _call_rows(day, label, *prices, expiry=expiry)
    (folder / f"{day}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_vix(repo: Path, closes: dict[str, float]) -> None:
    folder = repo / "context" / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    lines = [VIX_HEADER]
    for day, close in closes.items():
        lines.append(f"{day} 03:45:00+00:00,{close},{close},{close},{close},0,{close}")
    (folder / "_INDIAVIX.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _log(repo: Path) -> dict[str, dict[str, str]]:
    snaps = sl.read_snapshots(repo / "bidask")
    closes = {}
    vix_file = repo / "context" / "daily" / "_INDIAVIX.csv"
    if vix_file.is_file():
        closes = sl.parse_vix_closes(vix_file.read_text(encoding="utf-8"))
    return {row["entry_date"]: row for row in sl.build_log(snaps, closes)}


# Entry on 2026-11-02 at 10:15: sold bid 100, bought ask 40, so the credit is 60 points.
# Same-day 14:30 and 15:00 marks cost 55 and 55, so they decide nothing.
ENTRY = {
    "1015": (100, 101, 39, 40),
    "1430": (90, 91, 35, 36),
    "1500": (90, 91, 35, 36),
}


def test_ist_date_and_expiry_and_previous_vix():
    assert sl.ist_date("2026-10-29 18:45:00+00:00") == date(2026, 10, 30)
    assert sl.parse_expiry("17-NOV-26") == date(2026, 11, 17)
    closes = {date(2026, 10, 29): 15.0, date(2026, 11, 2): 22.0}
    # strictly the previous session, with its date
    assert sl.previous_vix(closes, date(2026, 11, 2)) == (date(2026, 10, 29), 15.0)
    assert sl.previous_vix({}, date(2026, 11, 2)) is None


def test_target_hit_next_session_1015(tmp_path):
    _write_day(tmp_path, "2026-11-02", ENTRY)
    # Next session 10:15: cost to close = 25 - 10 = 15, which is at most 31% of 60 (18.6).
    _write_day(tmp_path, "2026-11-03", {"1015": (20, 25, 10, 12)})
    row = _log(tmp_path)["2026-11-02"]
    assert row["status"] == "closed"
    assert row["exit_reason"] == "target"
    assert row["exit_stamp"] == "2026-11-03 10:16:00"
    assert row["exit_value_points"] == "15.00"
    assert row["credit_points"] == "60.00"
    assert row["gross_rupees"] == f"{(60 - 15) * rule.LOT:.2f}"
    assert row["note"] == sl.NOTE


def test_stop_hit_next_session_1430(tmp_path):
    _write_day(tmp_path, "2026-11-02", ENTRY)
    # Next session 10:15 cost 70 - 10 = 60 holds; 14:30 cost 200 - 10 = 190 reaches 2.5 x 60.
    _write_day(
        tmp_path,
        "2026-11-03",
        {"1015": (60, 70, 10, 12), "1430": (190, 200, 10, 12)},
    )
    row = _log(tmp_path)["2026-11-02"]
    assert row["status"] == "closed"
    assert row["exit_reason"] == "stop"
    assert row["exit_stamp"] == "2026-11-03 14:30:00"
    assert row["exit_value_points"] == "190.00"
    assert row["gross_rupees"] == f"{(60 - 190) * rule.LOT:.2f}"


def test_time_exit_on_next_session_1500(tmp_path):
    _write_day(tmp_path, "2026-11-02", ENTRY)
    # Cost to close never reaches the target (18.6) or the stop (150) before 15:00.
    _write_day(
        tmp_path,
        "2026-11-03",
        {
            "1015": (60, 80, 30, 31),
            "1430": (50, 70, 20, 21),
            "1500": (70, 90, 20, 21),
        },
    )
    row = _log(tmp_path)["2026-11-02"]
    assert row["status"] == "closed"
    assert row["exit_reason"] == "time"
    assert row["exit_stamp"] == "2026-11-03 15:00:00"
    assert row["exit_value_points"] == "70.00"
    assert row["gross_rupees"] == f"{(60 - 70) * rule.LOT:.2f}"


def test_open_when_next_session_does_not_exist(tmp_path):
    _write_day(tmp_path, "2026-11-02", ENTRY)
    row = _log(tmp_path)["2026-11-02"]
    assert row["status"] == "open"
    assert row["exit_reason"] == ""
    assert row["exit_stamp"] == ""
    assert row["exit_value_points"] == ""
    assert row["gross_rupees"] == ""
    assert row["credit_points"] == "60.00"
    assert row["note"] == sl.NOTE_NO_NEXT


def test_expiry_day_entry_is_skipped_by_the_window(tmp_path):
    # Entry on 2026-11-03 with the 03-NOV expiry: zero days to expiry, outside one to six.
    _write_day(tmp_path, "2026-11-03", ENTRY)
    row = _log(tmp_path)["2026-11-03"]
    assert row["status"] == "skipped"
    assert row["skipped_reason"] == sl.REASON_EXPIRY_WINDOW
    assert row["skipped_reason"] == "The nearest expiry is not one to six days away."
    assert row["exit_reason"] == ""
    assert row["gross_rupees"] == ""


def test_stale_vix_is_not_applied_and_says_so(tmp_path):
    # VIX close is from 2026-10-29. Entry 2026-11-07 is 9 days later: stale, so no gate.
    _write_day(tmp_path, "2026-11-07", ENTRY, expiry="10-NOV-26")
    _write_vix(tmp_path, {"2026-10-29": 25.0})
    row = _log(tmp_path)["2026-11-07"]
    assert row["status"] == "open"  # a VIX of 25 would have skipped a fresh series
    assert row["skipped_reason"] == ""
    assert row["vix_prev"] == ""
    assert row["note"] == f"{sl.NOTE_STALE_VIX} {sl.NOTE_NO_NEXT}"


def test_fresh_vix_within_five_days_still_gates(tmp_path):
    # Entry 2026-11-02 is 4 days after the 2026-10-29 close: not stale, so the gate applies.
    _write_day(tmp_path, "2026-11-02", ENTRY)
    _write_vix(tmp_path, {"2026-10-29": 25.0})
    row = _log(tmp_path)["2026-11-02"]
    assert row["status"] == "skipped"
    assert row["skipped_reason"] == rule.REASON_VIX_HIGH
    assert row["vix_prev"] == "25.00"
    assert "stale" not in row["note"]


def test_next_file_too_far_away_stays_open(tmp_path):
    # Entry 2026-11-02 (expiry 03-NOV). The next file is 5 days later, beyond the 4-day limit,
    # even though it holds the expiry and would otherwise stop the position at 14:30.
    _write_day(tmp_path, "2026-11-02", ENTRY)
    _write_day(
        tmp_path,
        "2026-11-07",
        {"1015": (60, 70, 10, 12), "1430": (190, 200, 10, 12)},
    )
    row = _log(tmp_path)["2026-11-02"]
    assert row["status"] == "open"
    assert row["exit_reason"] == ""
    assert row["note"] == sl.NOTE_NO_NEXT


def test_skipped_by_high_vix_is_logged_with_its_reason(tmp_path):
    _write_day(tmp_path, "2026-11-02", ENTRY)
    _write_day(tmp_path, "2026-11-03", {"1015": (20, 25, 10, 12)})
    _write_vix(tmp_path, {"2026-10-30": 21.0})
    row = _log(tmp_path)["2026-11-02"]
    assert row["status"] == "skipped"
    assert row["skipped_reason"] == rule.REASON_VIX_HIGH
    assert row["vix_prev"] == "21.00"
    assert row["credit_points"] == "60.00"
    assert row["exit_reason"] == ""
    assert row["gross_rupees"] == ""


def test_day_with_only_later_snapshots_gets_no_row(tmp_path):
    _write_day(tmp_path, "2026-11-02", ENTRY)
    _write_day(tmp_path, "2026-11-04", {"1430": (60, 61, 10, 11)})
    assert sorted(_log(tmp_path)) == ["2026-11-02"]


def test_merge_replaces_by_entry_date_and_sorts():
    old = [
        {"entry_date": "2026-11-03", "status": "open"},
        {"entry_date": "2026-11-02", "status": "open"},
    ]
    new = [{"entry_date": "2026-11-02", "status": "closed"}]
    merged = sl.merge_rows(old, new)
    assert [r["entry_date"] for r in merged] == ["2026-11-02", "2026-11-03"]
    assert merged[0]["status"] == "closed"


def test_dry_run_prints_and_writes_nothing(tmp_path, capsys):
    _write_day(tmp_path, "2026-11-02", ENTRY)
    assert sl.main([str(tmp_path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "2026-11-02" in out
    assert "dry run" in out
    assert not (tmp_path / "recorder").exists()


def test_write_is_idempotent_by_entry_date(tmp_path):
    _write_day(tmp_path, "2026-11-02", ENTRY)
    assert sl.main([str(tmp_path)]) == 0
    assert sl.main([str(tmp_path)]) == 0
    log = tmp_path / "recorder" / sl.LOG_NAME
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].split(",") == sl.COLUMNS
    assert len(lines) == 2  # header plus one entry, not duplicated by the second run


def test_missing_bidask_folder_is_an_error(tmp_path):
    assert sl.main([str(tmp_path)]) == 2
