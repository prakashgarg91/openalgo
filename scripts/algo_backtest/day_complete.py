"""Decide whether a trading day's automatic run finished, so the computer may be switched off.

Reads log/capture.log and the bid-ask file in the data repository. Exit 0 only when every part of the
day is in place; any other exit leaves the computer on. Read only; places no order.

    uv run python scripts/algo_backtest/day_complete.py <data_repo> [YYYY-MM-DD]
"""

import csv
import re
import sys
from datetime import date, datetime
from pathlib import Path

LABELS = ("1015", "1430", "1500")
FAILED_ZERO = re.compile(r"'failed': 0\}")


def todays_block(log_text: str, day: date) -> str:
    """The text of the last run that started on ``day`` (header ``==== DD-MM-YYYY HH:MM``)."""
    stamp = day.strftime("%d-%m-%Y")
    starts = [m.start() for m in re.finditer(r"^==== ", log_text, re.M)]
    starts.append(len(log_text))
    block = ""
    for a, b in zip(starts, starts[1:], strict=False):
        if log_text[a : a + 20].startswith(f"==== {stamp}"):
            block = log_text[a:b]
    return block


def judge(log_text: str, day: date, labels_seen: set[str], early: bool = False) -> list[str]:
    """Problems that stop the shutdown; an empty list means the day is complete.

    ``early`` is a day the trader chose to close before the market ended: the later bid-ask snapshots and
    the full-day candle check cannot be there, so only the 10:15 snapshot and a clean capture are required.
    """
    problems = []
    block = todays_block(log_text, day)
    if not block:
        return [f"no capture run found in the log for {day.isoformat()}"]
    if "'candles'" not in block or "'no_data'" not in block:
        problems.append("the option capture result line is missing")
    if "'candles'" in block and not FAILED_ZERO.search(block.split("'index_candles'")[0]):
        problems.append("the option capture reported failures")
    if "'index_candles'" not in block:
        problems.append("the index, VIX and ETF context line is missing")
    elif not FAILED_ZERO.search(block[block.index("'index_candles'") :].split("\n")[0]):
        problems.append("the index, VIX and ETF context reported failures")
    if "ETF ledgers" not in block:
        problems.append("the ETF ledger report is missing")
    if not early and "Everything the forward tests need from this day is in place." not in block:
        problems.append("the nightly data check did not pass")
    if f"Snapshot written: historify-{day.strftime('%Y%m%d')}" not in block:
        problems.append("the database snapshot was not written")
    missing = [x for x in (LABELS[:1] if early else LABELS) if x not in labels_seen]
    if missing:
        problems.append("bid-ask snapshots missing: " + ", ".join(missing))
    return problems


def labels_in(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as fh:
        return {str(row.get("label")) for row in csv.DictReader(fh)}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    repo = Path(args[0])
    day = date.fromisoformat(args[1]) if len(args) > 1 else datetime.now().date()
    log = Path(__file__).resolve().parents[2] / "log" / "capture.log"
    text = (
        log.read_text(encoding="utf-8", errors="replace").replace("\r", "") if log.exists() else ""
    )
    early = "--early" in sys.argv
    problems = judge(text, day, labels_in(repo / "bidask" / f"{day.isoformat()}.csv"), early)
    if problems:
        print(f"Day {day.isoformat()} is NOT complete:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"Day {day.isoformat()} is complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
