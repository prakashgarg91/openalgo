"""Parsing of NSE's daily futures and options archive files (docs/algos/nse-eod-registration.md).

Two layouts exist: the older daily file up to 5 July 2024 and the unified file from 8 July 2024.
Both are reduced to the same columns for Nifty index futures and options only. Pure functions: no
network and no clock; ``scripts/algo_backtest/fetch_nse_fo_eod.py`` does the fetching.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pandas as pd

HOST = "https://nsearchives.nseindia.com"
LAST_LEGACY_DAY = date(2024, 7, 5)
COLUMNS = [
    "date", "instrument", "expiry", "strike", "kind", "open", "high", "low", "close", "settle",
    "contracts", "open_interest", "change_in_oi", "underlying",
]  # fmt: skip
SYMBOL = "NIFTY"


def url_for(day: date) -> str:
    if day <= LAST_LEGACY_DAY:
        mon = f"{day:%b}".upper()
        return f"{HOST}/content/historical/DERIVATIVES/{day:%Y}/{mon}/fo{day:%d}{mon}{day:%Y}bhav.csv.zip"
    return f"{HOST}/content/fo/BhavCopy_NSE_FO_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"


def read_zip(payload: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = archive.namelist()[0]
        with archive.open(name) as handle:
            return pd.read_csv(handle)


def normalize(frame: pd.DataFrame) -> pd.DataFrame:
    """Nifty index futures and options rows in the common columns, whichever layout came in."""
    if "TckrSymb" in frame.columns:  # unified layout
        rows = frame[(frame["TckrSymb"] == SYMBOL) & frame["FinInstrmTp"].isin(["IDF", "IDO"])]
        out = pd.DataFrame(
            {
                "date": pd.to_datetime(rows["TradDt"]).dt.strftime("%Y-%m-%d"),
                "instrument": rows["FinInstrmTp"].map({"IDF": "FUTIDX", "IDO": "OPTIDX"}),
                "expiry": pd.to_datetime(rows["XpryDt"]).dt.strftime("%Y-%m-%d"),
                "strike": pd.to_numeric(rows["StrkPric"], errors="coerce"),
                "kind": rows["OptnTp"],
                "open": rows["OpnPric"], "high": rows["HghPric"], "low": rows["LwPric"],
                "close": rows["ClsPric"], "settle": rows["SttlmPric"],
                "contracts": rows["TtlTradgVol"], "open_interest": rows["OpnIntrst"],
                "change_in_oi": rows["ChngInOpnIntrst"], "underlying": rows["UndrlygPric"],
            }
        )  # fmt: skip
    else:  # older layout
        frame = frame.rename(columns=lambda c: c.strip())
        rows = frame[(frame["SYMBOL"] == SYMBOL) & frame["INSTRUMENT"].isin(["FUTIDX", "OPTIDX"])]
        out = pd.DataFrame(
            {
                "date": pd.to_datetime(rows["TIMESTAMP"], format="%d-%b-%Y").dt.strftime("%Y-%m-%d"),
                "instrument": rows["INSTRUMENT"],
                "expiry": pd.to_datetime(rows["EXPIRY_DT"], format="%d-%b-%Y").dt.strftime("%Y-%m-%d"),
                "strike": pd.to_numeric(rows["STRIKE_PR"], errors="coerce"),
                "kind": rows["OPTION_TYP"],
                "open": rows["OPEN"], "high": rows["HIGH"], "low": rows["LOW"],
                "close": rows["CLOSE"], "settle": rows["SETTLE_PR"],
                "contracts": rows["CONTRACTS"], "open_interest": rows["OPEN_INT"],
                "change_in_oi": rows["CHG_IN_OI"], "underlying": float("nan"),
            }
        )  # fmt: skip
    out["kind"] = out["kind"].where(out["instrument"] == "OPTIDX", "")
    out.loc[out["instrument"] == "FUTIDX", "strike"] = 0.0
    return out[COLUMNS].reset_index(drop=True)
