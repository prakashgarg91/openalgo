"""Record the day's Sandbox account (balance, positions, orders, trades) and the profit so far.

Read only: it calls the app's own read endpoints with the trader's API key and places no order. It
refuses to record when the app is in Live mode, so a Live account is never mixed into the Sandbox
series. One dated JSON per day (the raw replies) and one summary row appended to summary.csv in
<data_repo>/recorder/. Run by a Windows task at 15:40 on trading days, or by hand.

Usage: uv run python scripts/algo_backtest/record_account.py <data_repo> [--force]
Exit 0 when saved, 1 on a problem (the reason is printed).
"""

import csv
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import sandbox_round_trips as rt  # noqa: E402

HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")
SUMMARY_COLUMNS = [
    "date",
    "recorded_at",
    "mode",
    "available_cash",
    "used_margin",
    "realized_pnl",
    "unrealized_pnl",
    "total_pnl",
    "open_positions",
    "trades_today",
    "orders_today",
]


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


def number(value) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def call(http: httpx.Client, path: str, key: str) -> dict:
    reply = http.post(HOST + path, json={"apikey": key}).json()
    if reply.get("status") != "success":
        raise RuntimeError(f"{path}: {reply.get('message', 'not accepted')}")
    return reply


def summarise(now: datetime, mode: str, funds: dict, positions, trades, orders) -> dict:
    f = funds.get("data") or {}
    realized, unrealized = number(f.get("m2mrealized")), number(f.get("m2munrealized"))
    open_positions = [p for p in (positions.get("data") or []) if number(p.get("quantity")) != 0]
    return {
        "date": now.strftime("%Y-%m-%d"),
        "recorded_at": now.isoformat(timespec="seconds"),
        "mode": mode,
        "available_cash": number(f.get("availablecash")),
        "used_margin": number(f.get("utiliseddebits")),
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "total_pnl": round(realized + unrealized, 2),
        "open_positions": len(open_positions),
        "trades_today": len(trades.get("data") or []),
        "orders_today": len((orders.get("data") or {}).get("orders") or []),
    }


TRIP_COLUMNS = [
    "symbol",
    "side",
    "quantity",
    "entry_date",
    "entry_time",
    "exit_date",
    "exit_time",
    "entry_price",
    "exit_price",
    "gross",
    "charges",
    "slippage",
    "net_after_charges",
    "net_after_charges_and_slippage",
]
DAY_COLUMNS = [
    "entry_date",
    "trips",
    "gross",
    "charges",
    "slippage",
    "net_after_charges",
    "net_after_charges_and_slippage",
]


def write_round_trips(out: Path) -> str:
    """Every closed Sandbox position, net of charges and dated by the day it was OPENED.

    Reads the Sandbox database read only (db/sandbox.db, or ALGO_SANDBOX_DB) and rewrites two files:
    round_trips.csv and by_entry_date.csv. The account's own profit figure is gross, so this is the
    figure to judge by. Returns one line for the log.
    """
    path = Path(
        os.getenv("ALGO_SANDBOX_DB", str(Path(__file__).resolve().parents[2] / "db" / "sandbox.db"))
    )
    if not path.exists():
        return "No Sandbox database found, so no round trips were written."
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "select symbol, action, quantity, price, trade_timestamp from sandbox_trades order by trade_timestamp"
        ).fetchall()
    finally:
        conn.close()
    fills = [
        {"symbol": r[0], "action": r[1], "quantity": r[2], "price": r[3], "timestamp": str(r[4])}
        for r in rows
    ]
    result = rt.round_trips(fills)
    days = rt.by_entry_date(result["trips"])
    for name, columns, data in (
        ("round_trips.csv", TRIP_COLUMNS, result["trips"]),
        ("by_entry_date.csv", DAY_COLUMNS, days),
    ):
        with (out / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(data)
    net = round(sum(d["net_after_charges"] for d in days), 2)
    return (
        f"Round trips: {len(result['trips'])} closed, {len(result['open'])} open fill(s); "
        f"net after charges {net} (gross {round(sum(d['gross'] for d in days), 2)})."
    )


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    now = datetime.now()
    if now.weekday() >= 5 and "--force" not in sys.argv:
        print("Weekend: nothing to record. Use --force to test.")
        return 0
    key = read_key()
    if not key:
        print("The OpenAlgo API key is not set for this Windows user. Nothing was recorded.")
        return 1
    out = Path(args[0]) / "recorder"
    try:
        with httpx.Client(timeout=30) as http:
            mode_reply = http.post(HOST + "/api/v1/analyzer", json={"apikey": key}).json()
            analyze = (mode_reply.get("data") or {}).get("analyze_mode")
            if mode_reply.get("status") != "success" or analyze is None:
                print("Could not read the mode from OpenAlgo. Is it running and signed in?")
                return 1
            if not analyze:
                print(
                    "OpenAlgo is in Live mode. Nothing recorded: this recorder is for Sandbox only."
                )
                return 1
            raw = {
                "funds": call(http, "/api/v1/funds", key),
                "positions": call(http, "/api/v1/positionbook", key),
                "trades": call(http, "/api/v1/tradebook", key),
                "orders": call(http, "/api/v1/orderbook", key),
            }
    except (httpx.HTTPError, ValueError, RuntimeError) as why:
        print(f"Could not read the account: {why}")
        return 1
    row = summarise(now, "sandbox", raw["funds"], raw["positions"], raw["trades"], raw["orders"])
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{row['date']}_account.json").write_text(
        json.dumps(raw, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    summary = out / "summary.csv"
    rows = []
    if summary.exists():
        with summary.open(encoding="utf-8", newline="") as handle:
            rows = [r for r in csv.DictReader(handle) if r["date"] != row["date"]]
    rows.append({k: row[k] for k in SUMMARY_COLUMNS})
    with summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(write_round_trips(out))
    print(
        f"Saved {row['date']}: cash {row['available_cash']}, profit and loss today {row['total_pnl']}, "
        f"{row['open_positions']} open position(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
