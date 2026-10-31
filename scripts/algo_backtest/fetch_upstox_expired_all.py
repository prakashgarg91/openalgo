"""Download 5-minute candles of expired weekly Nifty options into a data repository, one expiry at a time.

Unlike fetch_upstox_expired.py this needs no local history folders: the expiry list and the Nifty
daily range come from Upstox itself. Each finished expiry is packed as one archive
(``bars5m/<expiry>.tar.gz``), listed in ``MANIFEST.csv`` and committed and pushed, so a lost session
resumes with the expiries already stored skipped. Read only towards Upstox; places no order.

Needs the Upstox Plus plan and a read-only token in UPSTOX_ANALYTICS_TOKEN (never printed).

Usage:
    uv run python scripts/algo_backtest/fetch_upstox_expired_all.py <data_repo> [start] [end] [--dry-run]
"""

import argparse
import csv
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.algo_backtest import fetch_upstox_expired as f  # noqa: E402

WINDOW_DAYS = 7
SPREAD_REACH = f.WIDTH + f.MARGIN


def get_expiries(client: httpx.Client) -> list[date]:
    data = f.get_json(client, "/v2/expired-instruments/expiries", {"instrument_key": f.UNDERLYING})
    return sorted(datetime.strptime(d, "%Y-%m-%d").date() for d in data.get("data", []))


def nifty_range(client: httpx.Client, first: date, last: date) -> tuple[float, float] | None:
    """(lowest low, highest high) of the Nifty index from Upstox daily candles, or None."""
    key = "NSE_INDEX%7CNifty%2050"
    path = f"/v3/historical-candle/{key}/days/1/{last:%Y-%m-%d}/{first:%Y-%m-%d}"
    rows = (f.get_json(client, path).get("data") or {}).get("candles", [])
    if not rows:
        return None
    return min(float(r[3]) for r in rows), max(float(r[2]) for r in rows)


def stored(repo: Path) -> set[str]:
    manifest = repo / "MANIFEST.csv"
    if not manifest.exists():
        return set()
    with manifest.open(encoding="utf-8") as handle:
        return {row["expiry"] for row in csv.DictReader(handle)}


def record(repo: Path, expiry: date, files: int, rows: int) -> None:
    manifest = repo / "MANIFEST.csv"
    new = not manifest.exists()
    with manifest.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(["expiry", "contracts", "rows", "stored_on"])
        writer.writerow([f"{expiry:%Y-%m-%d}", files, rows, date.today().isoformat()])


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def push(repo: Path, message: str) -> None:
    git(repo, "add", "bars5m", "MANIFEST.csv")
    git(repo, "commit", "-q", "-m", message)
    for attempt in range(4):
        try:
            git(repo, "push", "-q", "origin", "HEAD:main")
            return
        except subprocess.CalledProcessError:
            time.sleep(2 * 2**attempt)
    raise SystemExit("Could not push to the data repository; nothing is lost, run this again.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("start", nargs="?", default="2024-10-01")
    parser.add_argument("end", nargs="?", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.6)
    args = parser.parse_args()
    token = os.getenv("UPSTOX_ANALYTICS_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("Set UPSTOX_ANALYTICS_TOKEN to your Upstox read-only token first.")
        return 1
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    done = stored(args.repo)
    (args.repo / "bars5m").mkdir(exist_ok=True)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    total_calls = 0
    with httpx.Client(base_url=f.BASE, headers=headers, timeout=60) as client:
        try:
            expiries = [e for e in get_expiries(client) if start <= e <= end]
            for expiry in expiries:
                if f"{expiry:%Y-%m-%d}" in done:
                    continue
                first = expiry - timedelta(days=WINDOW_DAYS)
                span = nifty_range(client, first, expiry)
                if span is None:
                    print(f"{expiry}: no Nifty candles; skipped")
                    continue
                low = (span[0] - SPREAD_REACH) // 50 * 50
                high = -(-(span[1] + SPREAD_REACH) // 50) * 50
                item = (
                    pd.Timestamp(expiry),
                    pd.Timestamp(first),
                    float(low),
                    float(high),
                )
                with tempfile.TemporaryDirectory() as scratch:
                    out = Path(scratch)
                    result = f.run(
                        client, [item], out, args.sleep, args.dry_run, log=lambda *_: None
                    )
                    total_calls += result["calls"]
                    if args.dry_run:
                        continue
                    if result["files"] == 0:
                        print(f"{expiry}: no contract data came back; not stored")
                        continue
                    rows = sum(sum(1 for _ in p.open()) - 1 for p in out.glob("*.csv"))
                    archive = args.repo / "bars5m" / f"{expiry:%Y-%m-%d}.tar.gz"
                    with tarfile.open(archive, "w:gz") as tar:
                        for path in sorted(out.glob("*.csv")):
                            tar.add(path, arcname=path.name)
                record(args.repo, expiry, result["files"], rows)
                push(args.repo, f"data: 5-minute candles for the {expiry:%Y-%m-%d} expiry")
                print(f"{expiry}: {result['files']} contracts, {rows} rows stored")
        except f.FetchError as error:
            print(f"Stopped: {error}")
            return 2
    if args.dry_run:
        print(f"{len(expiries)} expiries, {total_calls} requests (not counting stored ones)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
