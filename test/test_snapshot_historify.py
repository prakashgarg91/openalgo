"""The Historify snapshot copy: names, rotation and a real copy of a small database."""

import importlib.util
from pathlib import Path

import duckdb
import pytest

SPEC = importlib.util.spec_from_file_location(
    "snapshot_historify",
    Path(__file__).resolve().parents[1] / "scripts/algo_backtest/snapshot_historify.py",
)
snap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snap)


def test_the_file_name_carries_the_date_and_rejects_a_bad_one():
    assert snap.snapshot_name("2026-10-30") == "historify-20261030.duckdb"
    with pytest.raises(ValueError):
        snap.snapshot_name("30-10-2026")


def test_only_the_newest_snapshots_are_kept(tmp_path):
    for day in ("20261001", "20261002", "20261003", "20261004"):
        (tmp_path / f"historify-{day}.duckdb").write_text("x")
    (tmp_path / "other.duckdb").write_text("x")  # never touched
    removed = snap.prune(tmp_path, keep=2)
    assert [p.name for p in removed] == ["historify-20261001.duckdb", "historify-20261002.duckdb"]
    assert sorted(p.name for p in tmp_path.glob("*.duckdb")) == [
        "historify-20261003.duckdb",
        "historify-20261004.duckdb",
        "other.duckdb",
    ]


def test_a_copy_has_the_same_rows_and_leaves_the_source_alone(tmp_path):
    source = tmp_path / "live.duckdb"
    con = duckdb.connect(str(source))
    con.execute("CREATE TABLE market_data (symbol VARCHAR, timestamp BIGINT, close DOUBLE)")
    con.execute("INSERT INTO market_data VALUES ('NIFTY', 1, 10.5), ('NIFTY', 2, 11.0)")
    con.close()
    target = tmp_path / "copy.duckdb"
    snap.copy_database(source, target)
    copy = duckdb.connect(str(target), read_only=True)
    assert copy.execute("SELECT count(*), sum(close) FROM market_data").fetchone() == (2, 21.5)
    copy.close()
    check = duckdb.connect(str(source), read_only=True)
    assert check.execute("SELECT count(*) FROM market_data").fetchone() == (2,)
    check.close()
