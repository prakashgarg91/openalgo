"""Run the one rejection screen of a registered end-of-day idea (docs/algos/algo-builder-v2.md).

The idea must be in the register, not yet run, and must describe its structure in its settings (legs,
cadence, move_filter) and carry the six standard gates. The screen runs once on the NSE end-of-day data
in the private data repository, over the primary period (expiries 1 April 2021 to 26 September 2024);
the overlap period is reported and decides nothing. The result is written into the registration with the
engine's seal and can only say rejected or eligible for a forward test. A second run is refused.
Read only apart from that record; places no order.

Usage:
    uv run python scripts/algo_backtest/screen_registration.py <data_repo> <registration_id>
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.algo_backtest import eight_structure_screen as base  # noqa: E402
from services.algos import eod_screen as es  # noqa: E402
from services.algos import nse_lots, registry  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    repo, record_id = Path(sys.argv[1]), sys.argv[2]
    folder = Path(os.getenv("ALGO_REGISTRY_DIR", "db/algo_registry"))
    record = registry.get(folder, record_id)
    if record is None:
        print("No such registration.")
        return 2
    if record["run"] is not None or record["status"] != "registered":
        print(
            "This registration has already been run. A second look is a new idea and a new trial."
        )
        return 2
    if not registry.intact(record):
        print("This registration was changed after it was frozen, so it cannot be run.")
        return 2
    try:
        es.spec_from_params(record["content"]["name"], record["content"]["params"])
        if list(record["content"]["gates"]) != list(es.GATE_TEXT):
            raise ValueError(
                "The registered gates must be exactly: " + ", ".join(es.GATE_TEXT) + "."
            )
    except ValueError as why:
        print(f"Nothing was run: {why}")
        return 2
    chain = es.Chain(base.load_options(repo))
    nifty = base.load_daily(repo / "context" / "daily" / "_NSEI.csv")
    vix = base.load_daily(repo / "context" / "daily" / "_INDIAVIX.csv")
    out = es.screen_registration(
        record, chain, nifty, vix, nse_lots.nifty_lot, base.PRIMARY, base.OVERLAP
    )
    done = registry.record_run(folder, record_id, out["results"], datetime.now(), out["seal"])
    (folder / f"{record_id}.screen.txt").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )
    stats = out["primary"]["stats"]
    print(f"{record['content']['name']}: {done['run']['verdict']}")
    print(
        f"  primary period: {stats['trades']} trades, net {stats['net']:,.0f}, at twice costs "
        f"{stats['net_2x']:,.0f}, drawdown {stats['drawdown']:,.0f}"
    )
    for gate, ok in out["results"].items():
        print(f"  {'passed' if ok else 'FAILED'}: {gate}")
    print("A pass here only makes the idea eligible for a forward test. Nothing is proven.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
