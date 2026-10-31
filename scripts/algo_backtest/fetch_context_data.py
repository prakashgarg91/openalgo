"""Download foreign-market, commodity, currency, sector and heavyweight-stock history into the data repository.

Daily bars for every series (the full history Yahoo serves, asked for by explicit dates because range=max returns monthly bars), plus hourly (about two years) and
5-minute (about 60 days, a rolling window that is gone later, so it is snapshotted) bars for the
key series, whose timing decides what was known before a 10:15 India entry. Read only; no order.
Nothing needs a login or a token.

Usage:
    uv run python scripts/algo_backtest/fetch_context_data.py <data_repo>

Output: <data_repo>/context/daily|hourly|min5/<symbol>.csv, and context/MANIFEST.csv. Re-running
refreshes every file.
"""

import csv
import sys
import time
from datetime import date
from pathlib import Path

import httpx
import pandas as pd

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0"}

GROUPS = {
    "us_risk": ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "^TNX", "^FVX", "^IRX", "DX-Y.NYB"],
    "us_futures": ["ES=F", "NQ=F", "YM=F", "RTY=F"],
    "fx": ["USDINR=X", "EURUSD=X", "USDJPY=X", "USDCNY=X", "GBPUSD=X", "AUDUSD=X"],
    "commodities": ["CL=F", "BZ=F", "GC=F", "SI=F", "HG=F", "NG=F"],
    "asia": ["^N225", "^HSI", "^KS11", "000001.SS", "^TWII", "^STI", "^AXJO"],
    "europe": ["^FTSE", "^GDAXI", "^FCHI", "^STOXX50E"],
    "overseas_india_etfs": ["INDA", "EPI", "EEM", "FXI"],
    "india_indices": [
        "^NSEI",
        "^NSEBANK",
        "^INDIAVIX",
        "^BSESN",
        "^CNXIT",
        "^CNXPHARMA",
        "^CNXAUTO",
        "^CNXFMCG",
        "^CNXMETAL",
        "^CNXENERGY",
        "^CNXREALTY",
        "^CNXPSUBANK",
        "^CNXMEDIA",
        "^CNXINFRA",
        "^CNXFIN",
    ],
    "india_heavyweights": [
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "RELIANCE.NS",
        "INFY.NS",
        "TCS.NS",
        "ITC.NS",
        "LT.NS",
        "SBIN.NS",
        "AXISBANK.NS",
        "BHARTIARTL.NS",
        "KOTAKBANK.NS",
        "HINDUNILVR.NS",
        "BAJFINANCE.NS",
        "MARUTI.NS",
        "SUNPHARMA.NS",
        "TATAMOTORS.NS",
        "M&M.NS",
        "NTPC.NS",
        "ONGC.NS",
        "TATASTEEL.NS",
    ],
}
KEY = [
    "^NSEI",
    "^NSEBANK",
    "^INDIAVIX",
    "^GSPC",
    "^IXIC",
    "^VIX",
    "ES=F",
    "NQ=F",
    "^N225",
    "^HSI",
    "^KS11",
    "000001.SS",
    "CL=F",
    "BZ=F",
    "GC=F",
    "DX-Y.NYB",
    "USDINR=X",
    "^TNX",
]
LAYERS = {"daily": ("1d", None), "hourly": ("1h", "730d"), "min5": ("5m", "60d")}


def fetch(client: httpx.Client, symbol: str, interval: str, span: str) -> pd.DataFrame:
    for attempt in range(4):
        try:
            params = {"interval": interval, "includePrePost": "false"}
            if span is None:
                # range=max silently coarsens to monthly bars; explicit dates keep them daily
                params.update(period1=0, period2=int(time.time()))
            else:
                params["range"] = span
            r = client.get(URL.format(symbol=symbol), params=params)
            if r.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            if r.status_code != 200:
                return pd.DataFrame()
            result = (r.json().get("chart", {}).get("result") or [None])[0]
            if not result or not result.get("timestamp"):
                return pd.DataFrame()
            quote = result["indicators"]["quote"][0]
            frame = pd.DataFrame(
                {k: quote.get(k) for k in ("open", "high", "low", "close", "volume")},
                index=pd.to_datetime(result["timestamp"], unit="s", utc=True),
            )
            adj = (result["indicators"].get("adjclose") or [{}])[0].get("adjclose")
            if adj is not None:
                frame["adjclose"] = adj
            frame.index.name = "timestamp_utc"
            return frame.dropna(subset=["close"])
        except httpx.HTTPError:
            time.sleep(3 * (attempt + 1))
    return pd.DataFrame()


def safe(symbol: str) -> str:
    return symbol.replace("^", "_").replace("=", "_").replace("/", "_").replace("&", "_")


def main() -> int:
    repo = Path(sys.argv[1])
    out = repo / "context"
    rows = []
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for group, symbols in GROUPS.items():
            for symbol in symbols:
                for layer, (interval, span) in LAYERS.items():
                    if layer != "daily" and symbol not in KEY:
                        continue
                    frame = fetch(client, symbol, interval, span)
                    time.sleep(0.4)
                    if frame.empty:
                        rows.append([group, symbol, layer, 0, "", "", "none"])
                        continue
                    folder = out / layer
                    folder.mkdir(parents=True, exist_ok=True)
                    frame.to_csv(folder / f"{safe(symbol)}.csv", float_format="%.6g")
                    rows.append(
                        [
                            group,
                            symbol,
                            layer,
                            len(frame),
                            frame.index[0].strftime("%Y-%m-%d"),
                            frame.index[-1].strftime("%Y-%m-%d"),
                            "ok",
                        ]
                    )
                    print(f"{symbol} {layer}: {len(frame)} rows", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "MANIFEST.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["group", "symbol", "layer", "rows", "first", "last", "status"])
        writer.writerows(rows)
        writer.writerow(["", "", "downloaded_on", date.today().isoformat(), "", "", ""])
    missing = [r for r in rows if r[6] == "none"]
    print(f"{len(rows) - len(missing)} series saved, {len(missing)} returned nothing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
