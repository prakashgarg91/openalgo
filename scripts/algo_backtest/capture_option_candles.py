"""Save today's 1-minute candles for the active weekly Nifty option contracts.

Run once each evening after the close (for example 16:00 IST, Monday to Friday) from cron or
the Historify scheduler's host. Reads with the Upstox Analytics token (no static IP) and writes
into the Historify database; places no order.

Usage:
    export UPSTOX_ANALYTICS_TOKEN=...
    uv run python scripts/algo_backtest/capture_option_candles.py [YYYY-MM-DD] [--dry-run]

--dry-run lists the contracts it would capture and makes no candle request for them.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from database.symbol import get_distinct_expiries  # noqa: E402
from services import option_capture as oc  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("day", nargs="?", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    token = os.getenv("UPSTOX_ANALYTICS_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("Set UPSTOX_ANALYTICS_TOKEN to your Upstox read-only token first.")
        return 1
    today = datetime.strptime(args.day, "%Y-%m-%d")
    expiry = oc.nearest_expiry(get_distinct_expiries(oc.EXCHANGE, oc.UNDERLYING, "options"), today)
    if expiry is None:
        print(
            "No Nifty option expiry found. Download the master contract first (log in to the broker)."
        )
        return 1
    history = oc.default_history(token)
    spot = oc.spot_from_index(history, args.day)
    if spot is None:
        print(f"No Nifty candles for {args.day}. It may be a market holiday; nothing was saved.")
        return 0
    contracts = oc.select_contracts(oc.option_rows(expiry), spot, expiry)
    print(f"{len(contracts)} contracts for the {expiry} expiry around Nifty {spot:.0f}")
    if args.dry_run:
        return 0
    result = oc.capture(contracts, args.day, history, oc.default_store())
    print(result)
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
