"""Run the registered forward shadow ledgers of the weekly call spread and print where they stand.

Reads one-minute candles already saved in the Historify database (see option-capture.md); places no
order and changes nothing there. Rules and pass gates are fixed in
docs/algos/forward-s3n-registration.md. Results are written to db/forward_s3n/.

Usage:
    uv run python scripts/algo_backtest/run_forward_s3n.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import forward_shadow_data as data  # noqa: E402
from services.algos import forward_weekly as fw  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "db" / "forward_s3n"


def main() -> int:
    bars, index, vix = data.load()
    days = bars.days()
    if not days or index.empty:
        print("No stored candles yet. Run capture_option_candles.py after a trading day first.")
        return 1
    results = fw.run(bars, index, vix)
    report = fw.build_report(results, index, days, pd.Timestamp.now().normalize())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    for name, ledger in report["ledgers"].items():
        rows = pd.DataFrame([{k: v for k, v in t.items() if k != "legs"} for t in ledger["trades"]])
        rows.to_csv(OUT / f"trades_{name}.csv", index=False)
    print(f"Forward shadow of the weekly call spread {fw.VERSION}: {len(days)} sessions stored.")
    print(f"First counted expiry {report['first_counted_expiry']}; sandbox mode, no order placed.")
    for name, ledger in report["ledgers"].items():
        skipped = ", ".join(f"{w['expiry']} {w['reason']}" for w in ledger["not_counted"]) or "none"
        print(
            f"  {name} ({ledger['width']}-point wing): {ledger['completed']} completed, "
            f"{ledger['still_open']} open, realistic net Rs {ledger['realistic_net']:,}, "
            f"not counted: {skipped}"
        )
    status = report["ledgers"]["L1"]["status"]
    print(
        f"  L1 status: {status['state']}" + (f", {status['verdict']}" if status["verdict"] else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
