"""Download NSE's end-of-day Nifty futures and options history (docs/algos/nse-eod-registration.md).

Public data from NSE's archive host; no login, no broker token, no order. Keeps only Nifty index
futures and options rows, one compressed table per year, plus a manifest of every date asked for
(ok, none for a weekend or holiday, failed for an error). Resumable: dates already in the manifest as
ok or none are skipped. Be polite: four workers and a short pause.

Usage:
    uv run python scripts/algo_backtest/fetch_nse_fo_eod.py <out_dir> [YYYY-MM-DD start] [YYYY-MM-DD end]
"""

import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import nse_eod as ne  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0"}
RETRIES = 3


def fetch_day(client: httpx.Client, day: date) -> tuple[date, str, pd.DataFrame | None]:
    for attempt in range(RETRIES):
        try:
            reply = client.get(ne.url_for(day))
            if reply.status_code == 404:
                return day, "none", None
            if reply.status_code == 200:
                return day, "ok", ne.normalize(ne.read_zip(reply.content))
        except (httpx.HTTPError, ValueError, OSError):
            pass
        time.sleep(2 * (attempt + 1))
    return day, "failed", None


def main() -> int:
    out = Path(sys.argv[1])
    start = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2015, 1, 1)
    end = date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else date.today() - timedelta(days=1)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "MANIFEST.csv"
    done: dict[str, dict] = {}
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8") as handle:
            done = {r["date"]: r for r in csv.DictReader(handle)}
    days = [
        start + timedelta(days=i)
        for i in range((end - start).days + 1)
        if (start + timedelta(days=i)).weekday() < 5
    ]
    todo = [d for d in days if done.get(f"{d:%Y-%m-%d}", {}).get("status") not in ("ok", "none")]
    print(f"{len(days)} weekdays asked for, {len(todo)} to fetch")
    fresh: dict[int, list[pd.DataFrame]] = {}
    with httpx.Client(timeout=60.0, headers=HEADERS, follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for n, (day, status, frame) in enumerate(
                pool.map(lambda d: fetch_day(client, d), todo), 1
            ):
                rows = 0 if frame is None else len(frame)
                done[f"{day:%Y-%m-%d}"] = {
                    "date": f"{day:%Y-%m-%d}",
                    "status": status,
                    "rows": rows,
                }
                if frame is not None and rows:
                    fresh.setdefault(day.year, []).append(frame)
                if n % 200 == 0:
                    print(f"  {n}/{len(todo)} fetched, last {day}")
    for year, frames in fresh.items():
        path = out / f"nifty_fo_{year}.csv.gz"
        new = pd.concat(frames)
        if path.exists():
            new = pd.concat([pd.read_csv(path), new])
        new = new.drop_duplicates(["date", "instrument", "expiry", "strike", "kind"]).sort_values(
            ["date", "instrument", "expiry", "strike", "kind"]
        )
        new.to_csv(path, index=False)
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "status", "rows"])
        writer.writeheader()
        writer.writerows(done[k] for k in sorted(done))
    counts = pd.Series([r["status"] for r in done.values()]).value_counts().to_dict()
    print(f"manifest: {counts}")
    return 0 if not counts.get("failed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
