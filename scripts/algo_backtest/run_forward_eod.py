"""Run the forward shadow ledgers of registered end-of-day structures (docs/algos/algo-builder-v2.md).

For every registration found eligible for a forward test that names one of the eight structures, fetch
the exchange's end-of-day files for the days since it was registered (public data, no login), replay the
structure with the screen's own engine and write db/forward_eod/<id>/report.json. When a test is stopped by
its kill rule or reaches its end, the verdict is recorded once in the registration. Places no order and
changes no algo, deployment or setting. Does nothing if no registration is waiting.

Usage:
    uv run python scripts/algo_backtest/run_forward_eod.py
"""

import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.algo_backtest import fetch_nse_fo_eod as fetch  # noqa: E402
from services.algos import eod_screen as es  # noqa: E402
from services.algos import forward_alerts as fa  # noqa: E402
from services.algos import forward_eod as fe  # noqa: E402
from services.algos import nse_lots, registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "db" / "forward_eod"
FILE = OUT / "nifty_fo_forward.csv.gz"
LEAD_DAYS = (
    20  # sessions before the first expiry are needed to find the entry day and the previous close
)


def _write_atomic(path: Path, text: str) -> None:
    """Replace the file in one step so a reader never sees half a report."""
    handle, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(text)
    os.replace(name, path)


def update_prices(start: date, end: date) -> pd.DataFrame:
    """The forward end-of-day table, extended with every weekday since the last stored one."""
    OUT.mkdir(parents=True, exist_ok=True)
    have = pd.read_csv(FILE) if FILE.exists() else pd.DataFrame()
    last = pd.Timestamp(have["date"].max()).date() if len(have) else None
    # Re-fetch the last week every night: a day that failed to download, or was not published yet,
    # is picked up again instead of being skipped for good (duplicates are dropped below).
    first = max(start, last - timedelta(days=7)) if last else start
    days = [first + timedelta(days=i) for i in range((end - first).days + 1)]
    days = [d for d in days if d.weekday() < 5]
    frames = []
    with httpx.Client(timeout=60.0, headers=fetch.HEADERS, follow_redirects=True) as client:
        for day in days:
            _day, status, frame = fetch.fetch_day(client, day)
            if status == "failed":
                print(
                    f"Could not fetch the end-of-day file for {day}; it will be tried again tomorrow."
                )
            elif frame is not None and len(frame):
                frames.append(frame)
    if frames:
        have = pd.concat([have, *frames], ignore_index=True).drop_duplicates(
            ["date", "instrument", "expiry", "strike", "kind"]
        )
        have.to_csv(FILE, index=False)
    return have


def main() -> int:
    folder = Path(os.getenv("ALGO_REGISTRY_DIR", "db/algo_registry"))
    waiting = [(r, fe.parse(r)) for r in registry._store(folder)]
    waiting = [(r, s) for r, s in waiting if s is not None]
    if not waiting:
        print("No registered idea is waiting for a forward test.")
        return 0
    from services.algos import forward_shadow_data as data

    _bars, index, vix = data.load()
    if index.empty:
        print("No stored Nifty candles yet. Run the nightly capture first.")
        return 1
    nifty = index["close"].groupby(index.index.normalize()).last()
    start = min(s["first_expiry"] for _r, s in waiting).date() - timedelta(days=LEAD_DAYS)
    prices = update_prices(start, date.today() - timedelta(days=1))
    if prices.empty:
        print("No forward end-of-day prices are stored yet.")
        return 1
    chain = es.Chain(prices)
    for record, settings in waiting:
        result = fe.run(settings, chain, nifty, vix, nse_lots.nifty_lot)
        out = fe.report(settings, result, chain.sessions, pd.Timestamp.now().normalize())
        target = OUT / record["id"]
        target.mkdir(parents=True, exist_ok=True)
        (target / "report.json").write_text(
            json.dumps(out, indent=2, default=str), encoding="utf-8"
        )
        print(
            f"{record['content']['name']} ({out['structure']}): {out['state']}, {out['completed']} completed, "
            f"{len(out['pending_expiries'])} expiries pending, lowest cumulative net Rs {out['lowest_cumulative_net']:,.0f}"
        )
        if out["verdict"]:
            registry.record_forward(
                folder,
                record["id"],
                out["verdict"],
                {"completed": out["completed"], "gates": out["gates"]},
                datetime.now(),
            )
            fa.notify(
                f"Forward test of {record['content']['name']} ended: {out['verdict']} after "
                f"{out['completed']} trades. Sandbox shadow only; nothing was traded."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
