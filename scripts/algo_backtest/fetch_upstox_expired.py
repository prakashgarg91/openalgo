"""Download 5-minute bars of expired Nifty weekly options from Upstox.

Needs Upstox's paid Plus plan: expired-contract history is not served on the free
plan. Read-only (GET only): it cannot place or change an order. The access token is
read from the environment and is never printed or written to a file.

For every weekly expiry in the window it lists that expiry's option contracts, keeps
the strikes a 400-point spread sold at the money could touch during the 8 days before
expiry (the range of the Nifty opens that week, plus the spread width and a margin),
and writes one file per contract: ``<expiry>_<CE|PE>_<strike>.csv`` with timestamp (IST
wall clock), open, high, low, close, volume, oi. Files already present are skipped, so
the download can be stopped and resumed.

The expiry dates and the Nifty opens come from the files the daily tests already use
(``fetch_history.py`` and ``fetch_nse_options.py``), so no expiry-list call is needed.

Usage:
    export UPSTOX_ANALYTICS_TOKEN=...      # or UPSTOX_ACCESS_TOKEN
    uv run python scripts/algo_backtest/fetch_upstox_expired.py \\
        <history_dir> <nse_days_dir> <out_dir> [start] [end] [--dry-run] [--sleep 0.6]
"""

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import lab  # noqa: E402

BASE = "https://api.upstox.com"
UNDERLYING = "NSE_INDEX|Nifty 50"
WIDTH = 400
MARGIN = 100
WINDOW_DAYS = 8


class FetchError(RuntimeError):
    """A failure with a message written for the person running the download."""


def _check(response: httpx.Response) -> dict:
    code = response.status_code
    if code == 401:
        raise FetchError(
            "Upstox did not accept the token. Create a fresh read-only token and export it again."
        )
    if code in (402, 403) or "UDAPI1149" in response.text:
        raise FetchError(
            "Your Upstox account does not include expired-contract history. It needs the Plus plan; "
            "upgrade it in your Upstox account and run this again."
        )
    if code == 429:
        raise FetchError("rate")
    if code >= 500:
        raise FetchError("Upstox is not answering right now. Run this again in a few minutes.")
    if code >= 400:
        raise FetchError(f"Upstox refused one request ({code}). It was skipped.")
    return response.json()


def get_json(client: httpx.Client, path: str, params: dict | None = None, retries: int = 4) -> dict:
    """GET with a pause and retry on rate limits. Raises FetchError in plain words."""
    for attempt in range(retries + 1):
        try:
            return _check(client.get(path, params=params))
        except FetchError as error:
            if str(error) != "rate" or attempt == retries:
                if str(error) == "rate":
                    raise FetchError(
                        "Upstox is limiting requests. Run this again later; it resumes."
                    ) from None
                raise
            time.sleep(2.0 * (attempt + 1))
        except httpx.HTTPError as error:
            if attempt == retries:
                raise FetchError(
                    "Could not reach Upstox. Check the connection and run this again."
                ) from error
            time.sleep(2.0 * (attempt + 1))
    raise FetchError("unreachable")


def parse_contracts(payload: dict) -> dict[tuple[str, float], str]:
    """{(kind, strike): instrument_key} from the option-contract listing."""
    rows = payload.get("data") or []
    if isinstance(rows, dict):
        rows = rows.get("contracts", [])
    out = {}
    for row in rows:
        kind = row.get("instrument_type") or row.get("option_type")
        strike = row.get("strike_price", row.get("strike"))
        key = row.get("instrument_key")
        if kind in ("CE", "PE") and strike is not None and key:
            out[(kind, float(strike))] = key
    return out


def parse_candles(payload: dict) -> pd.DataFrame:
    """Candle rows (newest first on the wire) to an ascending frame of IST wall-clock times."""
    data = payload.get("data") or {}
    rows = data.get("candles", []) if isinstance(data, dict) else data
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "oi"])
    frame = pd.DataFrame(rows).iloc[:, :7]
    frame.columns = ["timestamp", "open", "high", "low", "close", "volume", "oi"][: frame.shape[1]]
    stamps = (
        pd.to_datetime(frame["timestamp"], utc=True)
        .dt.tz_convert("Asia/Kolkata")
        .dt.tz_localize(None)
    )
    frame = frame.drop(columns="timestamp")
    frame.index = pd.DatetimeIndex(stamps, name="timestamp")
    return frame.sort_index()


def plan(history_dir: Path, nse_dir: Path, start: str | None, end: str | None):
    """[(expiry, window_start, strike_low, strike_high)] for every weekly expiry to download."""
    real = lab.load_real_prices(nse_dir)
    nifty = pd.read_csv(history_dir / "nsei.csv", parse_dates=["Date"]).set_index("Date")["Open"]
    weekly: dict[pd.Timestamp, list[pd.Timestamp]] = {}
    for day in sorted(real._days):
        if (start and day < pd.Timestamp(start)) or (end and day > pd.Timestamp(end)):
            continue
        near = next((e for e in real.expiries(day) if (e - day).days <= WINDOW_DAYS), None)
        if near is not None and day in nifty.index:
            weekly.setdefault(near, []).append(day)
    out = []
    for expiry, days in sorted(weekly.items()):
        opens = nifty.loc[days]
        low = (opens.min() - WIDTH - MARGIN) // 50 * 50
        high = -(-(opens.max() + WIDTH + MARGIN) // 50) * 50
        out.append((expiry, min(days), float(low), float(high)))
    return out


def run(client: httpx.Client, items, out_dir: Path, sleep: float, dry_run: bool, log=print) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    calls = files = skipped = missing = 0
    for expiry, first_day, low, high in items:
        wanted = [(kind, k) for k in _frange(low, high) for kind in ("CE", "PE")]
        todo = [
            w
            for w in wanted
            if not (out_dir / f"{expiry:%Y-%m-%d}_{w[0]}_{int(w[1])}.csv").exists()
        ]
        skipped += len(wanted) - len(todo)
        if not todo:
            continue
        if dry_run:
            calls += 1 + len(todo)
            continue
        contracts = parse_contracts(
            get_json(
                client,
                "/v2/expired-instruments/option/contract",
                {"instrument_key": UNDERLYING, "expiry_date": f"{expiry:%Y-%m-%d}"},
            )
        )
        calls += 1
        time.sleep(sleep)
        for kind, strike in todo:
            key = contracts.get((kind, strike))
            if key is None:
                missing += 1
                continue
            path = (
                f"/v2/expired-instruments/historical-candle/{quote(key, safe='')}"
                f"/5minute/{expiry:%Y-%m-%d}/{first_day:%Y-%m-%d}"
            )
            try:
                frame = parse_candles(get_json(client, path))
            except FetchError as error:
                if "refused one request" in str(error):
                    missing += 1
                    continue
                raise
            calls += 1
            time.sleep(sleep)
            if frame.empty:
                missing += 1
                continue
            frame.to_csv(out_dir / f"{expiry:%Y-%m-%d}_{kind}_{int(strike)}.csv")
            files += 1
        log(f"{expiry:%Y-%m-%d}: {files} files so far")
    return {"calls": calls, "files": files, "already_on_disk": skipped, "no_data": missing}


def _frange(low: float, high: float):
    value = low
    while value <= high:
        yield value
        value += 50


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("history_dir", type=Path)
    parser.add_argument("nse_days_dir", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("start", nargs="?")
    parser.add_argument("end", nargs="?")
    parser.add_argument(
        "--dry-run", action="store_true", help="count the requests without making any"
    )
    parser.add_argument("--sleep", type=float, default=0.6, help="seconds between requests")
    args = parser.parse_args()
    items = plan(args.history_dir, args.nse_days_dir, args.start, args.end)
    print(f"{len(items)} weekly expiries to cover")
    token = os.getenv("UPSTOX_ANALYTICS_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token and not args.dry_run:
        print("Set UPSTOX_ANALYTICS_TOKEN (or UPSTOX_ACCESS_TOKEN) to your Upstox token first.")
        return 1
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"} if token else {}
    with httpx.Client(base_url=BASE, headers=headers, timeout=30.0) as client:
        try:
            result = run(client, items, args.out_dir, args.sleep, args.dry_run)
        except FetchError as error:
            print(str(error))
            return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
