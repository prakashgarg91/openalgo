"""Save one bid and ask snapshot of the active weekly Nifty option chain.

Run three times on each trading day (10:15, 14:30 and 15:00 India time) by Windows tasks, or by
hand. Reads quotes with the Upstox Analytics token and appends rows to
<data_repo>/bidask/YYYY-MM-DD.csv. Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/snapshot_bidask.py <data_repo> <label> [--dry-run]
    (label is any short name for the moment, for example 1015, 1430 or 1500)
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from database.symbol import get_distinct_expiries  # noqa: E402
from services import bidask_snapshot as bs  # noqa: E402
from services import option_capture as oc  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 1
    repo, label = Path(args[0]), args[1]
    token = os.getenv("UPSTOX_ANALYTICS_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("Set UPSTOX_ANALYTICS_TOKEN to your Upstox read-only token first.")
        return 1
    now = datetime.now()
    expiry = oc.nearest_expiry(get_distinct_expiries(oc.EXCHANGE, oc.UNDERLYING, "options"), now)
    if expiry is None:
        print(
            "No Nifty option expiry found. Download the master contract first (log in to the broker)."
        )
        return 1
    from broker.upstox.api.data import BrokerData

    client = BrokerData(token)
    spot = float(client.get_quotes(oc.INDEX_SYMBOL, oc.INDEX_EXCHANGE).get("ltp") or 0)
    if spot <= 0:
        if now.weekday() < 5:
            print(
                "No Nifty price came back on a weekday. If the exchange is closed nothing is wrong; "
                "if not, Upstox did not accept the token or did not answer. Nothing was saved."
            )
            return 3
        print("Weekend: nothing was saved.")
        return 0
    contracts = oc.select_contracts(oc.option_rows(expiry), spot, expiry)
    print(f"{len(contracts)} contracts for the {expiry} expiry around Nifty {spot:.0f}")
    if "--dry-run" in sys.argv:
        return 0
    quotes = client.get_multiquotes(
        [{"symbol": c["symbol"], "exchange": oc.EXCHANGE} for c in contracts]
    )
    rows = bs.build_rows(quotes, contracts, spot, now.strftime("%Y-%m-%d %H:%M:%S"), label, expiry)
    if not rows:
        print("No quotes came back. Check the token, then run this again. Nothing was saved.")
        return 2
    target = repo / "bidask"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{now:%Y-%m-%d}.csv"
    frame = pd.DataFrame(rows, columns=bs.COLUMNS)
    frame.to_csv(path, mode="a", header=not path.exists(), index=False, float_format="%.6g")
    two_sided = int(frame["spread"].notna().sum())
    print(f"{len(rows)} quotes saved to {path.name}; {two_sided} with both a bid and an ask")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
