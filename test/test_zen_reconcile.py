"""Tests for scripts/algo_backtest/zen_reconcile.py using a tiny synthetic data repository."""

import io
import math
import sys
import tarfile
from datetime import UTC, date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "algo_backtest"))

import zen_reconcile as zr  # noqa: E402

from services.algos.zen_trades import IST, ZenTrade  # noqa: E402

HEADER = "timestamp,open,high,low,close,volume,oi\n"
EXPIRY = "2026-09-29"


def _csv(rows):
    lines = [HEADER]
    for stamp, open_, close in rows:
        lines.append(f"{stamp},{open_},{max(open_, close)},{min(open_, close)},{close},0,0\n")
    return "".join(lines)


def _write_archive(path: Path, members: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tar:
        for name, text in members.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Manifest lists three September and October expiries; only 2026-09-29 has candles.

    Sold PE 23000 and long PE 22900 carry decoy bars at 09:20 and 15:15 that a wrong bar choice
    would pick up. Sold PE 23100 is deliberately absent.
    """
    root = tmp_path / "data"
    root.mkdir()
    (root / "MANIFEST.csv").write_text(
        "expiry,contracts,rows,stored_on\n"
        "2026-09-08,10,100,2026-10-31\n"
        "2026-09-29,10,100,2026-10-31\n"
        "2026-10-06,10,100,2026-10-31\n",
        encoding="utf-8",
    )
    sold = _csv(
        [
            ("2026-09-10 09:15:00", 100, 102),
            ("2026-09-10 09:20:00", 200, 202),
            ("2026-09-10 15:15:00", 500, 500),
            ("2026-09-10 15:20:00", 20, 21),
        ]
    )
    long_ = _csv(
        [
            ("2026-09-10 09:15:00", 60, 61),
            ("2026-09-10 09:20:00", 70, 71),
            ("2026-09-10 15:15:00", 50, 50),
            ("2026-09-10 15:20:00", 5, 6),
        ]
    )
    _write_archive(
        root / "bars5m" / f"{EXPIRY}.tar.gz",
        {f"{EXPIRY}_PE_23000.csv": sold, f"{EXPIRY}_PE_22900.csv": long_},
    )
    return root


def _trade(advice_id, entry, exit_, **overrides) -> ZenTrade:
    fields = {
        "advice_id": advice_id,
        "entry_time": entry,
        "exit_time": exit_,
        "kind": "PE",
        "sold_symbol": "NIFTY2692923000PE",
        "long_symbol": "NIFTY2692922900PE",
        "sold_strike": 23000.0,
        "long_strike": 22900.0,
        "width": 100.0,
        "expiry": date(2026, 9, 29),
        "lots": 2,
        "lot_size": 65,
        "entry_credit": 42.0,
        "exit_debit": 14.0,
        "pnl": 1820.0,
        "margin": None,
        "exit_class": "time",
    }
    fields.update(overrides)
    return ZenTrade(**fields)


ENTRY = datetime(2026, 9, 10, 9, 17, 30, tzinfo=IST)
EXIT = datetime(2026, 9, 10, 15, 20, 10, tzinfo=IST)


def _manifest_expiries():
    return [date(2026, 9, 8), date(2026, 9, 29), date(2026, 10, 6)]


# ---- pure helpers -------------------------------------------------------------


def test_floor_to_5_takes_the_bar_start_in_ist_wall_clock():
    assert zr.floor_to_5(ENTRY) == pd.Timestamp("2026-09-10 09:15:00")
    assert zr.floor_to_5(EXIT) == pd.Timestamp("2026-09-10 15:20:00")
    assert zr.floor_to_5(datetime(2026, 9, 10, 15, 20, tzinfo=IST)) == pd.Timestamp(
        "2026-09-10 15:20:00"
    )


def test_floor_to_5_converts_utc_to_ist_before_flooring():
    # 03:47:30 UTC is 09:17:30 IST.
    stamp = datetime(2026, 9, 10, 3, 47, 30, tzinfo=UTC)
    assert zr.floor_to_5(stamp) == pd.Timestamp("2026-09-10 09:15:00")


def test_month_expiry_guess_picks_latest_expiry_in_the_symbol_month():
    expiries = _manifest_expiries()
    assert zr.month_expiry_guess("NIFTY26SEP23000PE", expiries) == date(2026, 9, 29)
    assert zr.month_expiry_guess("NIFTY26OCT23000PE", expiries) == date(2026, 10, 6)


def test_month_expiry_guess_returns_none_without_a_match():
    expiries = _manifest_expiries()
    assert zr.month_expiry_guess("NIFTY26DEC23000PE", expiries) is None
    assert zr.month_expiry_guess("NIFTY26SEP23000PE", []) is None
    assert zr.month_expiry_guess("garbage", expiries) is None
    # Weekly symbols carry their own day, so no guess is made for them.
    assert zr.month_expiry_guess("NIFTY2692923000PE", expiries) is None


def test_pair_bars_returns_none_for_missing_frame_or_bar(repo):
    legs = zr._read_expiry_archive(repo / "bars5m" / f"{EXPIRY}.tar.gz")
    sold, long_ = legs[("PE", 23000.0)], legs[("PE", 22900.0)]
    ts = pd.Timestamp("2026-09-10 09:15:00")
    bar_sold, bar_long = zr.pair_bars(sold, long_, ts)
    assert bar_sold["open"] == 100 and bar_long["close"] == 61
    assert zr.pair_bars(None, long_, ts) == (None, None)
    assert zr.pair_bars(sold, long_, pd.Timestamp("2026-09-10 09:00:00")) == (None, None)


def test_spread_points_is_sold_minus_long_and_none_when_missing():
    sold = pd.Series({"open": 100.0, "close": 102.0})
    long_ = pd.Series({"open": 60.0, "close": 61.0})
    assert zr.spread_points(sold, long_, "open") == 40.0
    assert zr.spread_points(sold, long_, "close") == 41.0
    assert zr.spread_points(None, long_, "close") is None


def _row(
    status="ok",
    zen_credit=None,
    our_credit_close=None,
    zen_debit=None,
    our_debit_close=None,
    zen_pnl=None,
    our_open=None,
    our_close=None,
    kind="PE",
):
    return {
        "status": status,
        "kind": kind,
        "zen_credit": zen_credit,
        "our_credit_close": our_credit_close,
        "zen_debit": zen_debit,
        "our_debit_close": our_debit_close,
        "zen_pnl_pts": zen_pnl,
        "our_pnl_pts_open": our_open,
        "our_pnl_pts_close": our_close,
    }


def test_summarize_rows_matches_a_hand_computed_example():
    rows = [
        # entry diffs (ours - zen): +1, -3, 0, +15
        _row(
            zen_credit=40,
            our_credit_close=41,
            zen_debit=10,
            our_debit_close=12,
            zen_pnl=30,
            our_open=28,
            our_close=29,
            kind="PE",
        ),
        _row(
            zen_credit=50,
            our_credit_close=47,
            zen_debit=10,
            our_debit_close=8,
            zen_pnl=40,
            our_open=38,
            our_close=39,
            kind="CE",
        ),
        _row(
            zen_credit=30,
            our_credit_close=30,
            zen_debit=10,
            our_debit_close=10,
            zen_pnl=20,
            our_open=20,
            our_close=21,
            kind="PE",
        ),
        _row(
            zen_credit=20,
            our_credit_close=35,
            zen_debit=10,
            our_debit_close=10,
            zen_pnl=10,
            our_open=10,
            our_close=10,
            kind="CE",
        ),
        # Not ok: must not enter any comparison.
        _row(status="no_exit_bar", zen_credit=1000, our_credit_close=0, kind="PE"),
    ]
    summary = zr.summarize_rows(rows)

    assert summary["trades"] == 5
    assert summary["status_counts"]["ok"] == 4
    assert summary["status_counts"]["no_exit_bar"] == 1
    assert summary["kind_counts"] == {"PE": 3, "CE": 2}
    assert summary["ok_kind_counts"] == {"PE": 2, "CE": 2}

    entry = summary["entry"]
    assert entry["n"] == 4
    assert entry["median"] == pytest.approx(0.5)  # sorted -3, 0, 1, 15
    assert entry["mean"] == pytest.approx(3.25)
    assert entry["abs_median"] == pytest.approx(2.0)  # sorted 0, 1, 3, 15
    assert entry["abs_mean"] == pytest.approx(4.75)
    assert entry["within_3"] == pytest.approx(0.75)  # 1, 0, 3 of 4
    assert entry["within_8"] == pytest.approx(0.75)  # 1, 3, 0 of 4; 15 is outside

    exit_ = summary["exit"]
    assert exit_["n"] == 4
    assert exit_["median"] == pytest.approx(0.0)  # diffs 2, -2, 0, 0
    assert exit_["mean"] == pytest.approx(0.0)
    assert exit_["abs_median"] == pytest.approx(1.0)  # abs 2, 2, 0, 0
    assert exit_["abs_mean"] == pytest.approx(1.0)
    assert exit_["within_3"] == pytest.approx(1.0)
    assert exit_["within_8"] == pytest.approx(1.0)

    pnl_close = summary["pnl_close"]
    assert pnl_close["n"] == 4
    assert pnl_close["zen_total"] == pytest.approx(100.0)
    assert pnl_close["our_total"] == pytest.approx(99.0)
    expected_corr = 475.0 / math.sqrt(500.0 * 452.75)
    assert pnl_close["correlation"] == pytest.approx(expected_corr)
    pnl_open = summary["pnl_open"]
    assert pnl_open["our_total"] == pytest.approx(96.0)


def test_summarize_rows_reports_none_not_zero_when_nothing_is_ok():
    summary = zr.summarize_rows([_row(status="no_expiry_data", kind="CE")])
    assert summary["entry"]["median"] is None
    assert summary["entry"]["within_3"] is None
    assert summary["pnl_close"]["correlation"] is None
    text = zr.format_summary(summary)
    assert "median signed difference: n/a" in text


# ---- end to end on the synthetic repository -----------------------------------


def _trades():
    return [
        # Monthly symbol, no day: guessed to the latest September expiry. Entry at 09:17:30
        # floors to 09:15; exit at 15:20:10 floors to 15:20.
        _trade(
            "A",
            ENTRY,
            EXIT,
            expiry=None,
            sold_symbol="NIFTY26SEP23000PE",
            long_symbol="NIFTY26SEP22900PE",
        ),
        # Exit at exactly 00:00 is a feed artifact: entry is still priced, exit is skipped.
        _trade("B", ENTRY, datetime(2026, 9, 10, 0, 0, tzinfo=IST)),
        # Exit time absent.
        _trade("H", ENTRY, None, exit_debit=None),
        # Sold leg file not in the archive.
        _trade("C", ENTRY, EXIT, sold_strike=23100.0),
        # Expiry not in the manifest.
        _trade("D", ENTRY, EXIT, expiry=date(2026, 12, 31)),
        # 09:00 bar does not exist.
        _trade("F", datetime(2026, 9, 10, 9, 0, tzinfo=IST), EXIT),
        # 15:25 bar does not exist.
        _trade("G", ENTRY, datetime(2026, 9, 10, 15, 25, 0, tzinfo=IST)),
    ]


def test_reconcile_trades_picks_bars_and_computes_points(repo):
    rows = {row["advice_id"]: row for row in zr.reconcile_trades(repo, _trades())}

    a = rows["A"]
    assert a["status"] == "ok"
    assert a["expiry"] == "2026-09-29"
    assert a["expiry_guess"] is True
    # Entry bar 09:15 (not the 09:20 decoy): sold 100/102, long 60/61.
    assert a["our_credit_open"] == pytest.approx(40.0)
    assert a["our_credit_close"] == pytest.approx(41.0)
    # Exit bar 15:20 (not the 15:15 decoy): sold 20/21, long 5/6.
    assert a["our_debit_open"] == pytest.approx(15.0)
    assert a["our_debit_close"] == pytest.approx(15.0)
    assert a["our_pnl_pts_open"] == pytest.approx(25.0)
    assert a["our_pnl_pts_close"] == pytest.approx(26.0)
    assert a["zen_credit"] == pytest.approx(42.0)
    assert a["zen_debit"] == pytest.approx(14.0)
    assert a["zen_pnl_pts"] == pytest.approx(28.0)
    assert a["zen_pnl_rupees"] == pytest.approx(1820.0)

    b = rows["B"]
    assert b["status"] == "no_exit_time"
    assert b["expiry_guess"] is False
    assert b["our_credit_close"] == pytest.approx(41.0)
    assert b["our_debit_open"] is None and b["our_debit_close"] is None
    assert b["our_pnl_pts_close"] is None

    assert rows["H"]["status"] == "no_exit_time"
    assert rows["H"]["zen_pnl_pts"] is None
    assert rows["C"]["status"] == "missing_leg_file"
    assert rows["C"]["our_credit_close"] is None
    assert rows["D"]["status"] == "no_expiry_data"
    assert rows["F"]["status"] == "no_entry_bar"
    assert rows["G"]["status"] == "no_exit_bar"
    assert rows["G"]["our_credit_close"] == pytest.approx(41.0)
    assert rows["G"]["our_debit_close"] is None


def test_reconcile_trades_keeps_input_order(repo):
    rows = zr.reconcile_trades(repo, _trades())
    assert [row["advice_id"] for row in rows] == ["A", "B", "H", "C", "D", "F", "G"]


def test_write_outputs_creates_csv_and_summary(repo, tmp_path):
    rows = zr.reconcile_trades(repo, _trades())
    summary = zr.summarize_rows(rows)
    out = repo / "research" / "zen_reconcile"
    text = zr.write_outputs(rows, summary, out)

    csv_text = (out / "trades.csv").read_text(encoding="utf-8").splitlines()
    assert csv_text[0].split(",") == list(zr.COLUMNS)
    assert len(csv_text) == 1 + len(rows)
    assert (out / "summary.txt").read_text(encoding="utf-8") == text
    assert "Trades: 7" in text
    # Missing values stay blank, not zero. Trade H has an entry bar but no exit time, so its
    # entry credit is filled while every exit-side and points cell stays empty.
    header = csv_text[0].split(",")
    h_line = next(line for line in csv_text if line.startswith("H,"))
    row_h = dict(zip(header, h_line.split(","), strict=True))
    assert row_h["status"] == "no_exit_time"
    assert row_h["our_credit_close"] == "41.0"
    assert row_h["our_debit_close"] == "" and row_h["zen_pnl_pts"] == ""
    assert row_h["exit_time"] == ""


def test_expiry_archive_is_read_once_per_expiry(repo, monkeypatch):
    calls = []
    original = zr._read_expiry_archive

    def spy(path):
        calls.append(path.name)
        return original(path)

    monkeypatch.setattr(zr, "_read_expiry_archive", spy)
    zr.reconcile_trades(repo, _trades())
    assert calls == [f"{EXPIRY}.tar.gz"]
