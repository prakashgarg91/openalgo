"""The recorder writes one by-entry-date view per Sandbox algo, beside the account-wide one."""

import csv
import sqlite3
from pathlib import Path

import pytest

from scripts.algo_backtest import record_account as ra

DAY = "2026-11-18"

# (symbol, action, quantity, price, trade_timestamp, strategy)
FILLS = [
    # ATM200-sandbox: a closed two-leg short spread, gross 1300 + 650 = 1950
    ("NIFTY18NOV2626000CE", "SELL", 65, 100, f"{DAY} 09:20:00", "ATM200-sandbox"),
    ("NIFTY18NOV2626000PE", "SELL", 65, 100, f"{DAY} 09:20:05", "ATM200-sandbox"),
    ("NIFTY18NOV2626000CE", "BUY", 65, 80, f"{DAY} 15:00:00", "ATM200-sandbox"),
    ("NIFTY18NOV2626000PE", "BUY", 65, 90, f"{DAY} 15:00:05", "ATM200-sandbox"),
    # Zen (algo): a closed short on another contract, gross 50 * 50 = 2500
    ("NIFTY18NOV2625500CE", "SELL", 50, 200, f"{DAY} 10:00:00", "Zen (algo)"),
    ("NIFTY18NOV2625500CE", "BUY", 50, 150, f"{DAY} 14:00:00", "Zen (algo)"),
    # No strategy recorded: a closed short, gross -300, written as "(none)"
    ("NIFTY18NOV2625000PE", "SELL", 10, 50, f"{DAY} 11:00:00", None),
    ("NIFTY18NOV2625000PE", "BUY", 10, 80, f"{DAY} 12:00:00", None),
    # Machinery test: must appear in neither clean file
    ("NIFTY18NOV2626500CE", "BUY", 75, 10, f"{DAY} 11:00:00", "kill-switch-test"),
    ("NIFTY18NOV2626500CE", "SELL", 75, 20, f"{DAY} 11:05:00", "kill-switch-test"),
]


@pytest.fixture
def sandbox_db(tmp_path, monkeypatch):
    path = tmp_path / "sandbox.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "create table sandbox_trades (symbol text, action text, quantity integer, "
        "price real, trade_timestamp text, strategy text)"
    )
    conn.executemany("insert into sandbox_trades values (?, ?, ?, ?, ?, ?)", FILLS)
    conn.commit()
    conn.close()
    monkeypatch.setenv("ALGO_SANDBOX_DB", str(path))
    return path


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_one_row_per_strategy_with_its_own_gross(sandbox_db, tmp_path):
    ra.write_round_trips(tmp_path)
    rows = read_csv(tmp_path / "by_strategy_entry_date.csv")
    assert [r["strategy"] for r in rows] == ["(none)", "ATM200-sandbox", "Zen (algo)"]
    gross = {r["strategy"]: float(r["gross"]) for r in rows}
    assert gross == {"(none)": -300.0, "ATM200-sandbox": 1950.0, "Zen (algo)": 2500.0}
    assert all(r["entry_date"] == DAY for r in rows)
    assert {r["strategy"]: int(r["trips"]) for r in rows} == {
        "(none)": 1,
        "ATM200-sandbox": 2,
        "Zen (algo)": 1,
    }


def test_per_strategy_nets_sum_to_the_account_day_net(sandbox_db, tmp_path):
    ra.write_round_trips(tmp_path)
    by_strategy = read_csv(tmp_path / "by_strategy_entry_date.csv")
    by_day = read_csv(tmp_path / "by_entry_date.csv")
    assert len(by_day) == 1 and by_day[0]["entry_date"] == DAY
    for column in ("net_after_charges", "net_after_charges_and_slippage", "gross"):
        total = round(sum(float(r[column]) for r in by_strategy), 2)
        assert total == pytest.approx(float(by_day[0][column]), abs=0.01), column


def test_account_day_view_has_no_strategy_column_and_keeps_all_clean_trips(sandbox_db, tmp_path):
    ra.write_round_trips(tmp_path)
    with (tmp_path / "by_entry_date.csv").open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == ra.DAY_COLUMNS
    assert "strategy" not in header
    assert int(read_csv(tmp_path / "by_entry_date.csv")[0]["trips"]) == 4


def test_rehearsal_fill_appears_in_no_clean_file(sandbox_db, tmp_path):
    ra.write_round_trips(tmp_path)
    clean_text = "".join(
        (tmp_path / name).read_text(encoding="utf-8")
        for name in ("round_trips.csv", "by_entry_date.csv", "by_strategy_entry_date.csv")
    )
    assert "kill-switch-test" not in clean_text
    assert "NIFTY18NOV2626500CE" not in clean_text
    test_trips = read_csv(tmp_path / "rehearsal_round_trips.csv")
    assert [t["symbol"] for t in test_trips] == ["NIFTY18NOV2626500CE"]


def test_log_line_names_each_algo_net(sandbox_db, tmp_path):
    line = ra.write_round_trips(tmp_path)
    assert "per algo: (none) net -" in line
    assert "ATM200-sandbox net " in line and "Zen (algo) net " in line
    assert line.endswith(".")


def test_account_files_are_written_identically_on_every_run(sandbox_db, tmp_path):
    ra.write_round_trips(tmp_path)
    first = {
        name: (tmp_path / name).read_bytes()
        for name in ("round_trips.csv", "by_entry_date.csv", "rehearsal_round_trips.csv")
    }
    other = tmp_path / "second"
    other.mkdir()
    ra.write_round_trips(other)
    for name, data in first.items():
        assert (other / name).read_bytes() == data
