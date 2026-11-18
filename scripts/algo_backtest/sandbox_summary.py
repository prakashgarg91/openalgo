"""Read-only 15:30 summary and status for the ATM 200 Sandbox bot.

It reads the bot's state, trades and log files and never calls OpenAlgo or places an order. This view
is read only and places no order.

Usage:
    uv run python scripts/algo_backtest/sandbox_summary.py summary [--date YYYY-MM-DD] [--notify]
    uv run python scripts/algo_backtest/sandbox_summary.py status

Options (both commands): --state PATH, --trades PATH, --log PATH to read other files than the
defaults under db/sandbox_bot_atm200/ and log/. --notify sends the summary through
services/algos/forward_alerts.notify (Telegram while the bot is on; always written to the log).
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from services.algos import sandbox_summary as ss  # noqa: E402

READ_ONLY = "This view is read only and places no order."
DEFAULT_STATE = ROOT / "db" / "sandbox_bot_atm200" / "state.json"
DEFAULT_TRADES = ROOT / "db" / "sandbox_bot_atm200" / "trades.csv"
DEFAULT_LOG = ROOT / "log" / "sandbox_bot_atm200.log"


def _read_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_trades(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_log(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("summary", "status"):
        p = sub.add_parser(name)
        p.add_argument("--state", type=Path, default=DEFAULT_STATE)
        p.add_argument("--trades", type=Path, default=DEFAULT_TRADES)
        p.add_argument("--log", type=Path, default=DEFAULT_LOG)
        if name == "summary":
            p.add_argument(
                "--date", default=None, help="The day to summarise, YYYY-MM-DD (default today)."
            )
            p.add_argument("--notify", action="store_true", help="Send the summary to Telegram.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    state = _read_state(args.state)
    log_lines = _read_log(args.log)

    if args.command == "status":
        print(READ_ONLY)
        print(json.dumps(state, indent=2, default=str))
        runs = ss.recent_runs(log_lines, 3)
        print("Last 3 log runs:" if runs else "No runs in the log yet.")
        for run in runs:
            print(run)
        return 0

    now_date = args.date or datetime.now().date().isoformat()
    summary = ss.build_summary(
        state, _read_trades(args.trades), log_lines, ss.EXPECTED_CHECKS, now_date
    )
    text = ss.render_text(summary)
    print(READ_ONLY)
    print(text)
    if args.notify:
        from services.algos import forward_alerts

        sent = forward_alerts.notify(text)
        print(
            "Sent to Telegram."
            if sent
            else "Not sent to Telegram: the bot is off or no user has notifications on. The text is in the log."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
