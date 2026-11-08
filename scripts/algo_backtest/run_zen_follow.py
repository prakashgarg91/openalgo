"""Nightly shadow follow ledger for Stratzy Zen's published advices. Read only: no orders are placed.

Reads the exported Zen advices file, follows every advice at one lot after charges, and writes
db/zen_follow/ (report.json, trades_all.csv, trades_calls.csv) under the current directory, so run
it from the repository root. The rules are in services/algos/zen_follow.py.

Usage:
    uv run python scripts/algo_backtest/run_zen_follow.py [zen_json]

The file is taken from the argument, else the ZEN_ADVICES_FILE environment variable, else the
default path below. A missing file is reported in one sentence and exits 0.
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from services.algos import zen_follow as zf  # noqa: E402
from services.algos.zen_trades import load_trades  # noqa: E402

DEFAULT_FILE = Path(
    r"D:\Github\trading-rex-ai\agent-results\stratzy-regime-study\trades\68596cd26aa2cba24bbb67da.jsonl"
)
FIELDS = [
    "advice_id",
    "entry_time",
    "kind",
    "sold_strike",
    "long_strike",
    "net",
    "net_2x",
    "unseen",
]
SECONDS_PER_DAY = 86_400
GATE_LABELS = (
    ("g1_net_positive", "Calls make money after charges"),
    ("g2_net_2x_positive", "Calls still make money at double the charges"),
    ("g3_drawdown_under_20000", "Calls' worst fall is under Rs 20,000"),
    ("g4_worst_day_above_minus_10000", "Calls' worst day is better than minus Rs 10,000"),
    ("g5_drawdown_below_zen_all", "Calls fall less than all advices together"),
)


def _rupees(value: float | None) -> str:
    return "n/a" if value is None else f"Rs {value:,.0f}"


def _print_summary(path: Path, age_days: float, rep: dict) -> None:
    seen, unseen, gate = rep["seen"], rep["unseen"], rep["gates"]
    print("Zen shadow follow ledger: one lot per advice, after charges. No orders placed.")
    print(f"  File: {path} (last changed {age_days:.1f} days ago)")
    print(
        f"  Advices in file: {rep['trades_in_file']} closed {seen['all']['trades']}, "
        f"open {rep['open_trades']}, not priced {rep['unpriced_trades']}."
    )
    print(
        f"  Entered on or before 23 Sep 2026 (seen): all {seen['all']['trades']} advices, "
        f"net {_rupees(seen['all']['net'])}; calls {seen['calls']['trades']}, "
        f"net {_rupees(seen['calls']['net'])}."
    )
    print(
        f"  Entered after 23 Sep 2026 (unseen): all {unseen['all']['trades']} advices, "
        f"net {_rupees(unseen['all']['net'])}; calls {unseen['calls']['trades']}, "
        f"net {_rupees(unseen['calls']['net'])}."
    )
    if gate["unseen_calls_trades"] == 0:
        print("  Checks on unseen calls: none yet, because no unseen call trade is in the file.")
    else:
        print("  Checks on unseen calls (not a verdict until 20 trades):")
        for key, label in GATE_LABELS:
            print(f"    {'pass' if gate[key] else 'fail'}: {label}")
    print(
        f"  Unseen call trades so far: {gate['unseen_calls_trades']}. Outcome: {gate['outcome']}."
    )
    if gate["outcome"] == "inconclusive":
        print(
            f"  Needs at least 20 unseen call trades before any verdict; {gate['trades_needed']} more to reach 30."
        )
    print(f"  {gate['note']}")
    if rep["stale_warning"]:
        print(f"  {rep['stale_warning']}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else Path(os.environ.get("ZEN_ADVICES_FILE") or DEFAULT_FILE)
    if not path.is_file():
        print(f"No Zen trade file at {path}, so nothing was run. The ledger runs once it is there.")
        return 0
    age_days = (time.time() - path.stat().st_mtime) / SECONDS_PER_DAY
    try:
        trades = load_trades(path)
    except (OSError, ValueError) as why:
        print(f"The Zen trade file at {path} could not be read ({why}). Nothing was written.")
        return 1

    rep = zf.report(trades, age_days)
    out = Path.cwd() / "db" / "zen_follow"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    for variant, name in (("all", "trades_all.csv"), ("calls", "trades_calls.csv")):
        with (out / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(zf.rows_for(trades, variant))
    _print_summary(path, age_days, rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
