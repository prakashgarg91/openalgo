"""Download NSE's daily F&O bhavcopy and keep only the Nifty option rows.

The bhavcopy has the real open and close price of every option contract each day,
which lets an overnight algo be tested on actual prices instead of a model. One
compact CSV per trading day is written; days already present are skipped, so the
download can be stopped and resumed.

Two formats exist: the old one until early July 2024 and the UDiFF one after. Both
are normalised to: date, expiry, strike, kind, open, close, volume, oi.

Set FETCH_KIND=futures to keep the Nifty index FUTURES rows instead (the same columns,
with strike and kind empty), for testing overnight futures positions.

Usage:
    uv run python scripts/algo_backtest/fetch_nse_options.py <history_dir> <out_dir> [start] [end]
"""

import io
import os
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}
NEW = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
OLD = "https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{d:%Y}/{m}/fo{d:%d}{m}{d:%Y}bhav.csv.zip"
KEEP_DAYS = 45


FUTURES = os.getenv("FETCH_KIND", "options") == "futures"


def parse_new(frame: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    rows = frame[
        (frame["TckrSymb"] == "NIFTY") & (frame["FinInstrmTp"] == ("IDF" if FUTURES else "IDO"))
    ]
    return pd.DataFrame(
        {
            "date": day,
            "expiry": pd.to_datetime(rows["XpryDt"]),
            "strike": rows["StrkPric"],
            "kind": rows["OptnTp"].map({"CE": "CE", "PE": "PE"}),  # empty for futures
            "open": rows["OpnPric"],
            "close": rows["ClsPric"],
            "volume": rows["TtlTradgVol"],
            "oi": rows["OpnIntrst"],
        }
    )


def parse_old(frame: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    rows = frame[
        (frame["INSTRUMENT"] == ("FUTIDX" if FUTURES else "OPTIDX")) & (frame["SYMBOL"] == "NIFTY")
    ]
    return pd.DataFrame(
        {
            "date": day,
            "expiry": pd.to_datetime(rows["EXPIRY_DT"], format="%d-%b-%Y"),
            "strike": rows["STRIKE_PR"],
            "kind": rows["OPTION_TYP"].map({"CE": "CE", "PE": "PE"}),
            "open": rows["OPEN"],
            "close": rows["CLOSE"],
            "volume": rows["CONTRACTS"],
            "oi": rows["OPEN_INT"],
        }
    )


def fetch_day(client: httpx.Client, day: pd.Timestamp) -> pd.DataFrame | None:
    for url, parser in (
        (NEW.format(d=day), parse_new),
        (OLD.format(d=day, m=day.strftime("%b").upper()), parse_old),
    ):
        for attempt in range(3):
            try:
                response = client.get(url, timeout=40)
            except httpx.HTTPError:
                time.sleep(1.5 * (attempt + 1))
                continue
            if response.status_code == 404:
                break
            if response.status_code != 200:
                time.sleep(1.5 * (attempt + 1))
                continue
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                frame = pd.read_csv(archive.open(archive.namelist()[0]))
            out = parser(frame, day)
            out = out[(out["expiry"] - day).dt.days.between(0, KEEP_DAYS)]
            return out if len(out) else None
    return None


def main() -> None:
    history_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    start = pd.Timestamp(sys.argv[3] if len(sys.argv) > 3 else "2023-01-01")
    end = pd.Timestamp(sys.argv[4] if len(sys.argv) > 4 else "2026-12-31")
    out_dir.mkdir(parents=True, exist_ok=True)
    nifty = pd.read_csv(history_dir / "nsei.csv", index_col=0, parse_dates=True)
    days = [d.tz_localize(None) if d.tzinfo else d for d in nifty.index if start <= d <= end]
    todo = [d for d in days if not (out_dir / f"{d:%Y%m%d}.csv").exists()]
    print(f"{len(days)} trading days, {len(todo)} to download", flush=True)
    done = 0

    def work(day):
        nonlocal done
        with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
            frame = fetch_day(client, day)
        if frame is not None:
            frame.to_csv(out_dir / f"{day:%Y%m%d}.csv", index=False)
        done += 1
        if done % 25 == 0:
            print(f"  {done}/{len(todo)}", flush=True)
        time.sleep(0.2)
        return frame is not None

    with ThreadPoolExecutor(max_workers=6) as pool:
        ok = sum(pool.map(work, todo))
    print(f"saved {ok} of {len(todo)} days", flush=True)


if __name__ == "__main__":
    main()
