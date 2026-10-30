"""Write a read-only snapshot copy of the Historify database after a capture, for other tools to read.

Why: DuckDB lets one writer hold the file, and a second process cannot open it meanwhile, so a research
tool reading db/historify.duckdb can be locked out by the app or the nightly capture. This copies the
finished day to db/snapshots/historify-YYYYMMDD.duckdb, which nothing writes to afterwards.

It reads the live file read-only (retrying while it is busy), writes the copy to a temporary name and
renames it when complete, and keeps the newest KEEP snapshots. Places no order and changes nothing in
Historify.

Usage:
    uv run python scripts/algo_backtest/snapshot_historify.py [YYYY-MM-DD]
"""

import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SOURCE = ROOT / "db" / "historify.duckdb"
OUT = ROOT / "db" / "snapshots"
KEEP = 30
RETRIES = 6
WAIT_SECONDS = 20


def snapshot_name(day: str) -> str:
    return f"historify-{datetime.strptime(day, '%Y-%m-%d').strftime('%Y%m%d')}.duckdb"


def prune(folder: Path, keep: int = KEEP) -> list[Path]:
    """Delete all but the newest ``keep`` snapshots (by name, which sorts by date). Returns the deleted."""
    found = sorted(folder.glob("historify-????????.duckdb"))
    old = found[:-keep] if keep > 0 else found
    for path in old:
        path.unlink()
    return old


def copy_database(source: Path, target: Path) -> None:
    """Copy every table of ``source`` (opened read-only) into a new database file ``target``."""
    import duckdb

    if target.exists():
        target.unlink()
    connection = duckdb.connect()
    try:
        connection.execute(f"ATTACH '{source.as_posix()}' AS src (READ_ONLY)")
        connection.execute(f"ATTACH '{target.as_posix()}' AS dst")
        connection.execute("COPY FROM DATABASE src TO dst")
        connection.execute("DETACH dst")
        connection.execute("DETACH src")
    finally:
        connection.close()


def main(argv: list[str]) -> int:
    day = argv[1] if len(argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    if not SOURCE.exists():
        print("No Historify database found yet. Run capture_option_candles.py first.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    final = OUT / snapshot_name(day)
    partial = final.with_suffix(".partial")
    for attempt in range(1, RETRIES + 1):
        try:
            copy_database(SOURCE, partial)
            partial.replace(final)
            break
        except Exception as why:
            partial.unlink(missing_ok=True)
            if "lock" not in str(why).lower() and "conflict" not in str(why).lower():
                raise  # not a busy file: do not hide a real fault behind a retry
            if attempt == RETRIES:
                print(
                    "The Historify database stayed busy, so no snapshot was written. "
                    "Close the OpenAlgo app and the capture, then run this again."
                )
                return 2
            time.sleep(WAIT_SECONDS)
    removed = prune(OUT)
    print(
        f"Snapshot written: {final.name} ({final.stat().st_size / 1e6:.1f} MB); removed {len(removed)} old."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
