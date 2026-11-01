"""NSE end-of-day archive parsing: both layouts reduce to the same Nifty-only table."""

import io
import zipfile
from datetime import date

import pandas as pd

from services.algos import nse_eod as ne

LEGACY = pd.DataFrame(
    {
        "INSTRUMENT": ["OPTIDX", "OPTIDX", "FUTIDX", "OPTSTK"],
        "SYMBOL": ["NIFTY", "BANKNIFTY", "NIFTY", "NIFTY"],
        "EXPIRY_DT": ["26-Mar-2015", "26-Mar-2015", "26-Mar-2015", "26-Mar-2015"],
        "STRIKE_PR": [8500.0, 18000.0, 0.0, 100.0],
        "OPTION_TYP": ["CE", "CE", "XX", "CE"],
        "OPEN": [100.0, 1, 8600.0, 1],
        "HIGH": [110.0, 1, 8650.0, 1],
        "LOW": [90.0, 1, 8580.0, 1],
        "CLOSE": [105.0, 1, 8620.0, 1],
        "SETTLE_PR": [104.0, 1, 8621.0, 1],
        "CONTRACTS": [500, 1, 900, 1],
        "VAL_INLAKH": [1, 1, 1, 1],
        "OPEN_INT": [7000, 1, 9000, 1],
        "CHG_IN_OI": [10, 1, -5, 1],
        "TIMESTAMP": ["05-Jan-2015"] * 4,
    }
)
UNIFIED = pd.DataFrame(
    {
        "TradDt": ["2026-10-30"] * 3, "TckrSymb": ["NIFTY", "NIFTY", "FINNIFTY"],
        "FinInstrmTp": ["IDO", "IDF", "IDO"], "XpryDt": ["2026-11-03"] * 3,
        "StrkPric": [23000.0, None, 23000.0], "OptnTp": ["PE", None, "PE"],
        "OpnPric": [50.0, 23100.0, 1], "HghPric": [60.0, 23200.0, 1], "LwPric": [40.0, 23000.0, 1],
        "ClsPric": [55.0, 23150.0, 1], "SttlmPric": [55.5, 23151.0, 1],
        "TtlTradgVol": [1000, 200, 1], "OpnIntrst": [5000, 300, 1],
        "ChngInOpnIntrst": [-20, 4, 1], "UndrlygPric": [23053.1] * 3,
    }
)  # fmt: skip


def test_the_older_layout_keeps_only_nifty_index_rows_in_common_columns():
    out = ne.normalize(LEGACY)
    assert list(out.columns) == ne.COLUMNS
    assert len(out) == 2 and set(out["instrument"]) == {"OPTIDX", "FUTIDX"}
    call = out[out["instrument"] == "OPTIDX"].iloc[0]
    assert (call["date"], call["expiry"], call["strike"], call["kind"]) == (
        "2015-01-05",
        "2015-03-26",
        8500.0,
        "CE",
    )
    assert call["settle"] == 104.0 and call["open_interest"] == 7000
    fut = out[out["instrument"] == "FUTIDX"].iloc[0]
    assert fut["strike"] == 0.0 and fut["kind"] == ""


def test_the_unified_layout_gives_the_same_columns_and_the_underlying_price():
    out = ne.normalize(UNIFIED)
    assert list(out.columns) == ne.COLUMNS and len(out) == 2
    put = out[out["instrument"] == "OPTIDX"].iloc[0]
    assert (put["date"], put["expiry"], put["strike"], put["kind"]) == (
        "2026-10-30",
        "2026-11-03",
        23000.0,
        "PE",
    )
    assert put["underlying"] == 23053.1 and put["settle"] == 55.5
    fut = out[out["instrument"] == "FUTIDX"].iloc[0]
    assert fut["strike"] == 0.0 and fut["kind"] == ""


def test_urls_follow_the_two_layouts_and_the_switch_date():
    assert ne.url_for(date(2015, 1, 5)).endswith("/2015/JAN/fo05JAN2015bhav.csv.zip")
    assert ne.url_for(date(2024, 7, 5)).endswith("/2024/JUL/fo05JUL2024bhav.csv.zip")
    assert ne.url_for(date(2024, 7, 8)).endswith("BhavCopy_NSE_FO_0_0_0_20240708_F_0000.csv.zip")


def test_a_zip_is_read_back_into_a_frame():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("fo.csv", LEGACY.to_csv(index=False))
    assert len(ne.read_zip(buffer.getvalue())) == 4
