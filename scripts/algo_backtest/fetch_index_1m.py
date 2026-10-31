"""Download Nifty 1-minute index candles from Upstox into the data repository (index/nifty_1m.csv).

Needed to replay the registered side rules on the expired option data. Read only; places no order.
Uses UPSTOX_ANALYTICS_TOKEN (never printed). Re-running refreshes the file.

Usage:
    uv run python scripts/algo_backtest/fetch_index_1m.py <data_repo> [start] [end]
"""

import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.algo_backtest import fetch_upstox_expired as f  # noqa: E402

KEY = "NSE_INDEX%7CNifty%2050"
CHUNK_DAYS = 28


def main() -> int:
    repo = Path(sys.argv[1])
    start = datetime.strptime(sys.argv[2] if len(sys.argv) > 2 else "2024-09-20", "%Y-%m-%d").date()
    end = datetime.strptime(sys.argv[3], "%Y-%m-%d").date() if len(sys.argv) > 3 else date.today()
    token = os.getenv("UPSTOX_ANALYTICS_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("Set UPSTOX_ANALYTICS_TOKEN to your Upstox read-only token first.")
        return 1
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    frames = []
    with httpx.Client(base_url=f.BASE, headers=headers, timeout=60) as client:
        cursor = start
        while cursor <= end:
            stop = min(cursor + timedelta(days=CHUNK_DAYS - 1), end)
            path = f"/v3/historical-candle/{KEY}/minutes/1/{stop:%Y-%m-%d}/{cursor:%Y-%m-%d}"
            frame = f.parse_candles(f.get_json(client, path))
            print(f"{cursor} to {stop}: {len(frame)} candles", flush=True)
            if not frame.empty:
                frames.append(frame)
            cursor = stop + timedelta(days=1)
            time.sleep(1.0)
    if not frames:
        print("Upstox returned no candles.")
        return 2
    out = pd.concat(frames)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    target = repo / "index"
    target.mkdir(exist_ok=True)
    out.to_csv(target / "nifty_1m.csv", float_format="%.6g")
    print(f"{len(out)} candles, {out.index[0]:%Y-%m-%d} to {out.index[-1]:%Y-%m-%d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
