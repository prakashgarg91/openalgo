"""Read-only readiness check before the Thursday dry run of the sandbox bot.

It reads OpenAlgo (mode, a Nifty quote, expiry, entry day, lot size, the two option quotes) and the
Windows scheduled tasks, then prints one line per check and a headline. It places no order and calls
no order endpoint. The API key is read from OPENALGO_API_KEY (or the Windows user variable) and is
never printed or written; the report shows only whether it is set.

Usage:
    uv run python scripts/algo_backtest/thursday_check.py

Exit code 0 when the dry run is ready, 1 otherwise.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import os
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import dryrun_check as dc  # noqa: E402
from services.algos import sandbox_bot as sb  # noqa: E402

# Api, holidays and nearest_expiry live in the bot script; load it by path so its directory
# never lands on sys.path.
_BOT_PATH = Path(__file__).resolve().parent / "sandbox_bot.py"
_spec = importlib.util.spec_from_file_location("algo_sandbox_bot_script", _BOT_PATH)
assert _spec is not None and _spec.loader is not None
bot_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bot_script)

IST = timezone(timedelta(hours=5, minutes=30))
TIMEOUT = 15.0
SPOT_SYMBOL = "NIFTY"
SPOT_EXCHANGE = "NSE_INDEX"
OPEN_TIME, CLOSE_TIME = time(9, 15), time(15, 30)


def read_key() -> str:
    key = os.getenv("OPENALGO_API_KEY", "")
    if key:
        return key
    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('OPENALGO_API_KEY','User')",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def app_up(host: str) -> bool:
    try:
        httpx.get(host.rstrip("/") + "/login", timeout=8.0)
    except httpx.HTTPError:
        return False
    return True


def positive(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def read_mode(api: bot_script.Api) -> str | None:
    try:
        reply = api.post("/api/v1/orderbook")
    except (sb.Refused, httpx.HTTPError):
        return None
    mode = reply.get("mode")
    if not isinstance(mode, str) or not mode:
        return None
    return "analyze" if mode == "analyze" else "live"


def read_spot(api: bot_script.Api) -> float | None:
    try:
        reply = api.post("/api/v1/quotes", symbol=SPOT_SYMBOL, exchange=SPOT_EXCHANGE)
    except (sb.Refused, httpx.HTTPError):
        return None
    data = reply.get("data") or {}
    if reply.get("status") != "success" or not positive(data.get("ltp")):
        return None
    return float(data["ltp"])


def read_expiry(api: bot_script.Api, today: date) -> date | None:
    try:
        return bot_script.nearest_expiry(api, today)
    except (sb.Refused, ValueError, httpx.HTTPError):
        return None


def read_entry_day(api: bot_script.Api, expiry: date | None, today: date) -> date | None:
    if expiry is None:
        return None
    try:
        return sb.entry_day(expiry, bot_script.holidays(api, today.year), sb.SESSIONS_BEFORE)
    except (sb.Refused, ValueError, httpx.HTTPError):
        return None


def read_lot(expiry: date | None) -> int | None:
    if expiry is None:
        return None
    try:
        return sb.lot_quantity(expiry)
    except (sb.Refused, ValueError):
        return None


def leg_quote(api: bot_script.Api, expiry: date, strike: int) -> dict:
    reply = api.post(
        "/api/v1/quotes", symbol=sb.contract_symbol(expiry, strike, "CE"), exchange=sb.EXCHANGE
    )
    return reply.get("data") or {}


def read_legs(api: bot_script.Api, expiry: date | None, spot: float | None) -> str:
    if expiry is None or spot is None:
        return "unknown"
    try:
        sold, long_strike = sb.strikes(spot)
        quotes = [leg_quote(api, expiry, strike) for strike in (sold, long_strike)]
    except (sb.Refused, ValueError, httpx.HTTPError):
        return "unknown"
    if all(positive(q.get("bid")) and positive(q.get("ask")) for q in quotes):
        return "two_sided"
    return "none"


def market_open(now: datetime) -> bool:
    local = now.astimezone(IST)
    return local.weekday() < 5 and OPEN_TIME <= local.time() <= CLOSE_TIME


def query_task(name: str) -> str | None:
    try:
        proc = subprocess.run(
            ["schtasks", "/query", "/tn", name, "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    first = next(csv.reader(io.StringIO(proc.stdout)), [])
    return first[1] if len(first) >= 2 else None


def read_tasks() -> dict[str, str | None]:
    return {name: query_task(name) for name in dc.REQUIRED_TASKS}


def neutral_facts(app: bool, key: bool, today: date, tasks: dict) -> dc.Facts:
    return dc.Facts(
        app_up=app,
        key_set=key,
        mode=None,
        quote_ok=False,
        today=today,
        expiry=None,
        entry_day=None,
        lot_qty=None,
        legs="unknown",
        market_open=False,
        tasks=tasks,
    )


def gather(host: str, key: str, today: date, now: datetime) -> dc.Facts:
    app = app_up(host)
    tasks = read_tasks()
    if not app or not key:
        return neutral_facts(app, bool(key), today, tasks)
    with httpx.Client(timeout=TIMEOUT) as http:
        api = bot_script.Api(http, host, key)
        spot = read_spot(api)
        expiry = read_expiry(api, today)
        return dc.Facts(
            app_up=True,
            key_set=True,
            mode=read_mode(api),
            quote_ok=spot is not None,
            today=today,
            expiry=expiry,
            entry_day=read_entry_day(api, expiry, today),
            lot_qty=read_lot(expiry),
            legs=read_legs(api, expiry, spot),
            market_open=market_open(now),
            tasks=tasks,
        )


def main() -> int:
    now = datetime.now(IST)
    host = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")
    facts = gather(host, read_key(), now.date(), now)
    rows = dc.evaluate(facts)
    print(f"Dry run readiness for {facts.today}")
    for level, check, message in rows:
        print(f"[{level.upper():4}] {check}: {message}")
    ready, headline = dc.summary(rows)
    print(headline)
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
