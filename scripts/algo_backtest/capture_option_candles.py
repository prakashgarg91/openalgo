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
    ranges = oc.index_ranges(history, args.day)
    spot = oc.spot_from_index(history, args.day)
    if spot is None:
        if today.weekday() < 5:
            # Upstox answers a refused token the same way as a holiday: with no candles at all.
            print(
                f"No Nifty candles came back for {args.day}, a weekday. If the exchange was closed "
                "that day nothing is wrong. If not, Upstox did not accept the analytics token or "
                "did not answer: check the token, then run this again. Nothing was saved."
            )
            return 3
        print(f"{args.day} is a weekend; nothing was saved.")
        return 0
    contracts = oc.select_contracts(
        oc.option_rows(expiry), spot, expiry, oc.reach_for(ranges, args.day)
    )
    print(f"{len(contracts)} contracts for the {expiry} expiry around Nifty {spot:.0f}")
    if args.dry_run:
        return 0
    store = oc.default_store()
    result = oc.capture(contracts, args.day, history, store)
    print(result)
    context = oc.capture_context(args.day, history, store)
    print(context)
    if result["stored"] == 0:
        print(
            "No option contract was saved. Upstox may have refused the token; check it and run again."
        )
        return 2
    return 0 if result["failed"] == 0 and context["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
