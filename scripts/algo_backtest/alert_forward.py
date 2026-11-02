"""Send the evening Telegram alerts for the forward shadow test (docs/algos/forward-s3n-registration.md).

Run by the nightly job after the capture and the ledger run, with the capture's exit code. Reads
only what is already stored and the ledger report; places no order.

Usage:
    uv run python scripts/algo_backtest/alert_forward.py <capture_exit_code> [YYYY-MM-DD]
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import forward_alerts as fa  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "db" / "forward_s3n"


def main() -> int:
    code = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    day = sys.argv[2] if len(sys.argv) > 2 else datetime.now().strftime("%Y-%m-%d")
    messages = []
    text = fa.capture_message(code, day)
    if text:
        messages.append(text)
    try:
        from services.algos import forward_shadow_data as data

        bars, _index, _vix = data.load()
        gap = fa.missing_day_message(bars.days(), datetime.strptime(day, "%Y-%m-%d").date())
        if gap:
            messages.append(gap)
    except Exception as err:
        messages.append(f"Could not read the stored candles to check for missed days: {err}")
    report_path, seen_path = OUT / "report.json", OUT / "alerted.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        seen = (
            set(json.loads(seen_path.read_text(encoding="utf-8"))) if seen_path.exists() else set()
        )
        new, seen = fa.events(report, seen)
        messages.extend(new)
        seen_path.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    for message in messages:
        print(f"ALERT: {message}")
        if not fa.notify(message):
            print(
                "(The Telegram bot is off or unreachable, so this alert was only written to the log.)"
            )
    if not messages:
        print("Forward test alerts: nothing new.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
