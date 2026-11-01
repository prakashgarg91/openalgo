"""Run the sandbox-mode executor of the weekly call spread (S3n) against a running OpenAlgo.

It only works while OpenAlgo is in analyzer (sandbox) mode and places no live order. Set
OPENALGO_API_KEY (and OPENALGO_HOST if OpenAlgo is not on http://127.0.0.1:5000) first.

Usage:
    uv run python scripts/algo_backtest/sandbox_bot.py entry   [--dry-run]   # at about 10:15 on the entry session
    uv run python scripts/algo_backtest/sandbox_bot.py check                 # at about 10:20 and 15:00
    uv run python scripts/algo_backtest/sandbox_bot.py exit    [--dry-run] [--force]   # at about 15:25 on the expiry session
    uv run python scripts/algo_backtest/sandbox_bot.py compare               # after the nightly ledger run
"""

import csv
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import forward_alerts as fa  # noqa: E402
from services.algos import sandbox_bot as sb  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "db" / "sandbox_bot" / "state.json"
COMPARE = ROOT / "db" / "sandbox_bot" / "compare.csv"
LEDGER = ROOT / "db" / "forward_s3n" / "report.json"


class Api:
    def __init__(self, http: httpx.Client, host: str, key: str):
        self.http, self.host, self.key = http, host.rstrip("/"), key

    def post(self, path: str, **payload) -> dict:
        try:
            reply = self.http.post(self.host + path, json={"apikey": self.key, **payload})
            return reply.json()
        except (httpx.HTTPError, ValueError) as err:
            raise sb.Refused(
                "OpenAlgo did not answer. Check that it is running and that OPENALGO_HOST is right."
            ) from err


def holidays(api: Api, year: int) -> set[date]:
    reply = api.post("/api/v1/market/holidays", year=year)
    return {
        date.fromisoformat(h["date"])
        for h in reply.get("data", [])
        if h.get("holiday_type") == "TRADING_HOLIDAY" and "NFO" in h.get("closed_exchanges", [])
    }


def nearest_expiry(api: Api, today: date) -> date:
    reply = api.post(
        "/api/v1/expiry", symbol=sb.UNDERLYING, exchange=sb.EXCHANGE, instrumenttype="options"
    )
    found = sorted(
        d
        for d in (datetime.strptime(x, "%d-%b-%y").date() for x in reply.get("data", []))
        if d >= today
    )
    if not found:
        raise sb.Refused("OpenAlgo has no Nifty option expiry; download the master contract first.")
    return found[0]


def compare_rows() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    if state.get("status") != "closed" or not LEDGER.exists():
        print("Nothing to compare yet: no closed bot week or no ledger report.")
        return 0
    trades = json.loads(LEDGER.read_text(encoding="utf-8"))["ledgers"]["L1"]["trades"]
    match = [t for t in trades if t["expiry"][:10] == state["expiry"]]
    if not match:
        print(f"The ledger has not closed the {state['expiry']} week yet.")
        return 0
    row = {"expiry": state["expiry"], **sb.compare(state, match[0])}
    new = not COMPARE.exists()
    COMPARE.parent.mkdir(parents=True, exist_ok=True)
    with COMPARE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        if new:
            writer.writeheader()
        writer.writerow(row)
    print(row)
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    command = args[0] if args else ""
    if command == "compare":
        return compare_rows()
    if command not in ("entry", "check", "exit"):
        print(__doc__)
        return 1
    key = os.getenv("OPENALGO_API_KEY")
    if not key:
        print("Set OPENALGO_API_KEY to your OpenAlgo API key first.")
        return 1
    dry = "--dry-run" in sys.argv
    with httpx.Client(timeout=15.0) as http:
        api = Api(http, os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000"), key)
        bot = sb.Bot(api, STATE, notify=fa.notify, sleep=time.sleep)
        try:
            if command == "entry":
                now = datetime.now()
                result = bot.enter(
                    nearest_expiry(api, now.date()), now, holidays(api, now.year), dry
                )
            elif command == "check":
                result = bot.check()
            else:
                result = bot.exit(dry, today=date.today(), force="--force" in sys.argv)
        except sb.Refused as why:
            print(str(why))
            return 2
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
