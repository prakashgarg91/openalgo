"""Synthetic-data checks for weekly_premium_vs_move: the premium-vs-move day, skips and buckets.

The repo is built inside tmp_path (a made-up January 2026 week), so nothing reads the real
data repository and nothing is written outside the test's own directory.
"""

import io
import sys
import tarfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.algo_backtest import weekly_premium_vs_move as wpm  # noqa: E402

EXPIRY = "2026-01-08"  # the only expiry in the synthetic manifest


def _write_expiry_tar(repo: Path, members: dict) -> None:
    with tarfile.open(repo / "bars5m" / f"{EXPIRY}.tar.gz", "w:gz") as tar:
        for name, bars in members.items():
            text = "timestamp,open,high,low,close,volume,oi\n" + "".join(
                f"{ts},50,50,50,{close},0,0\n" for ts, close in bars
            )
            buf = io.BytesIO(text.encode())
            info = tarfile.TarInfo(f"{name}.csv")
            info.size = len(buf.getvalue())
            tar.addfile(info, buf)


def make_repo(tmp_path: Path, vix=None) -> Path:
    repo = tmp_path / "data"
    (repo / "bars5m").mkdir(parents=True)
    (repo / "index").mkdir()
    (repo / "context" / "daily").mkdir(parents=True)
    # Sessions 01-02, 01-05, 01-06 (entry), 01-07 (skip) and 01-08 (expiry). Only the entry
    # day has a 10:15 Nifty bar; spot 25010 rounds (Python round) to the 25000 ATM strike.
    # The expiry-day 15:29 close is 25070, so the move is |25070 - 25010| = 60 points.
    nifty = [
        ("2026-01-02 09:15:00", 24000.0),
        ("2026-01-05 09:15:00", 24100.0),
        ("2026-01-06 10:15:00", 25010.0),
        ("2026-01-07 09:15:00", 24200.0),
        ("2026-01-08 15:29:00", 25070.0),
    ]
    pd.DataFrame(nifty, columns=["timestamp", "close"]).to_csv(
        repo / "index" / "nifty_1m.csv", index=False
    )
    # VIX closes per session; with vix_window=2 the 01-06 entry sees median(15, 16) = 15.5
    # against its previous-session 16, which lands at/above the median.
    if vix is None:
        vix = [
            ("2026-01-02 03:45:00+00:00", 15.0),
            ("2026-01-05 03:45:00+00:00", 16.0),
            ("2026-01-06 03:45:00+00:00", 17.0),
            ("2026-01-07 03:45:00+00:00", 18.0),
        ]
    pd.DataFrame(vix, columns=["timestamp_utc", "close"]).to_csv(
        repo / "context" / "daily" / "_INDIAVIX.csv", index=False
    )
    (repo / "MANIFEST.csv").write_text(
        "expiry,contracts,rows,stored_on\n2026-01-08,2,2,2026-01-09\n"
    )
    _write_expiry_tar(
        repo,
        {
            f"{EXPIRY}_CE_25000": [("2026-01-06 10:15:00", 50.0)],
            f"{EXPIRY}_PE_25000": [("2026-01-06 10:15:00", 50.0)],
        },
    )
    return repo


def test_straddle_100_move_60_counts_as_premium_gt_move(tmp_path):
    df, _ = wpm.collect(make_repo(tmp_path), vix_window=2)
    day = df[df.date == pd.Timestamp("2026-01-06")]
    assert len(day) == 1
    row = day.iloc[0]
    assert row.straddle == 100.0  # 50-point call close plus 50-point put close
    assert row.move == 60.0
    assert row.straddle > row.move
    assert round(row.ratio, 2) == 1.67
    s = wpm.stats(day)
    assert s == {
        "days": 1,
        "share_straddle_gt_move": 1.0,
        "mean_ratio": 1.67,
        "median_ratio": 1.67,
        "mean_straddle": 100.0,
        "mean_move": 60.0,
    }


def test_days_with_missing_values_are_skipped_and_counted(tmp_path):
    df, skips = wpm.collect(make_repo(tmp_path), vix_window=2)
    # 01-02, 01-05 and 01-07 are sessions with the expiry 1-6 days ahead but no 10:15 bar.
    assert sorted(df.date) == [pd.Timestamp("2026-01-06")]
    assert skips == {"nifty 10:15 spot missing": 3}


def test_dte_and_vix_buckets_and_summary(tmp_path):
    repo = make_repo(tmp_path)
    df, skips = wpm.collect(repo, vix_window=2)
    row = df.iloc[0]
    assert row.dte == 2 and row.dte_bucket == "1-2"
    assert row.vix_prev == 16.0 and row.vix_bucket == "at_above"
    summary = wpm.summarize(df, skips)
    assert summary["all"]["days"] == 1
    assert summary["vix_below"]["days"] == 0
    assert summary["vix_at_above"]["days"] == 1
    assert summary["dte_1-2"]["days"] == 1
    assert summary["dte_3-4"]["days"] == 0 and summary["dte_5-6"]["days"] == 0
    assert summary["skipped_days"] == 3
    assert summary["vix_bucket_missing_days"] == 0
    table = wpm.render(summary, repo)
    assert "all" in table and "skipped days: 3" in table


def test_vix_gap_inside_the_window_does_not_block_the_bucket(tmp_path):
    vix = [
        ("2026-01-05 03:45:00+00:00", 16.0),
        ("2026-01-06 03:45:00+00:00", 17.0),
        ("2026-01-07 03:45:00+00:00", 18.0),
    ]  # 01-02 has no VIX row
    df, _ = wpm.collect(make_repo(tmp_path, vix=vix), vix_window=2)
    row = df.iloc[0]
    # The median falls back to the closes present in the window: median(16) vs previous 16.
    assert row.vix_bucket == "at_above"


def test_day_after_a_vix_less_session_has_no_bucket_but_still_counts(tmp_path):
    vix = [
        ("2026-01-02 03:45:00+00:00", 15.0),
        ("2026-01-06 03:45:00+00:00", 17.0),
        ("2026-01-07 03:45:00+00:00", 18.0),
    ]  # 01-05, the entry day's previous session, has none
    df, _ = wpm.collect(make_repo(tmp_path, vix=vix), vix_window=2)
    assert len(df) == 1
    assert pd.isna(df.iloc[0].vix_prev) and df.iloc[0].vix_bucket is None
    summary = wpm.summarize(df, {})
    assert summary["all"]["days"] == 1
    assert summary["vix_bucket_missing_days"] == 1
