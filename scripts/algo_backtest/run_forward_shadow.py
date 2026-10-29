"""Run the registered forward shadow test over every stored day and print where it stands.

Reads candles already saved in the Historify database (see option-capture.md); places no order and
changes nothing there. The three rules and the pass gates are fixed in
docs/algos/forward-test-registration.md. Results are written to db/forward_shadow/.

Usage:
    uv run python scripts/algo_backtest/run_forward_shadow.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import forward_shadow as fs  # noqa: E402
from services.algos import forward_shadow_data as data  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "db" / "forward_shadow"
NAMES = {
    "A": "A, continuation",
    "B": "B, opening-move fade",
    "C": "C, always calls (control)",
}


def main() -> int:
    bars, index, vix = data.load()
    days = bars.days()
    if not days or index.empty:
        print("No stored candles yet. Run capture_option_candles.py after a trading day first.")
        return 1
    results = {rule: fs.simulate_rule(rule, bars, index, vix) for rule in fs.SIDE_RULES}
    report = fs.evaluate(results, days)
    OUT.mkdir(parents=True, exist_ok=True)
    for rule, result in results.items():
        rows = [{k: v for k, v in t.items() if k != "marks"} for t in result.trades]
        pd.DataFrame(rows).to_csv(OUT / f"trades_{rule}.csv", index=False)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"Forward shadow test {fs.VERSION}: {report['sessions']} sessions stored, ")
    print(
        f"the verdict is due at {fs.REGISTERED_SESSIONS}. Until then this is a progress read only."
    )
    for rule, result in results.items():
        net = sum(t["net"] for t in result.trades)
        skipped = ", ".join(f"{n} {why}" for why, n in result.skipped.items()) or "none"
        print(
            f"  Rule {NAMES[rule]}: {len(result.trades)} trades, net Rs {net:,.0f}, "
            f"{len(result.open_positions)} still open, skipped days: {skipped}"
        )
    for name in fs.CANDIDATES:
        gates = report[name]["gates"]
        failing = [g for g, ok in gates.items() if not ok]
        print(f"  Rule {name} gates not yet met: {', '.join(failing) if failing else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
