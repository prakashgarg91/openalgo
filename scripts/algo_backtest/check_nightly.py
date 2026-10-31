"""Check, the evening after the 16:00 capture, that the day's data really arrived.

A missed evening is silent: capture_option_candles.py fails alone at 16:00 and the forward tests
run on stale data days later. This script reads the Historify database and the two nightly report
files, then tells the trader in plain words what is missing and what to run. It reads only - it
places no order and changes nothing.

Usage:
    uv run python scripts/algo_backtest/check_nightly.py [YYYY-MM-DD]

Exit code 0 means every check passed, 2 means at least one check found a problem.
"""

import argparse
import re
import sys
import time
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.logging import get_logger  # noqa: E402

logger = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[2]

OK = "OK"
PROBLEM = "PROBLEM"

OPTION_EXCHANGE = "NFO"
INDEX_SYMBOL = "NIFTY"
INDEX_EXCHANGE = "NSE_INDEX"
VIX_SYMBOL = "INDIAVIX"
ETF_EXCHANGE = "NSE"
ETF_SYMBOLS = ("NIFTYBEES", "GOLDBEES")
INTRADAY = "1m"
DAILY = "D"

# A live weekly Nifty option, for example NIFTY26NOV2624500CE or NIFTY26DEC31245120.5PE.
OPTION_SYMBOL = re.compile(r"^NIFTY\d{2}[A-Z]{3}\d{2}\d+(\.\d+)?(CE|PE)$")
MIN_OPTION_CONTRACTS = 60
MIN_OPTION_CANDLES = 300
MIN_INDEX_CANDLES = 370
FULL_SESSION_CANDLES = 375  # 09:15 to 15:29, one candle a minute
MAX_ARTIFACT_AGE_HOURS = 36
VIX_MAX_GAP_DAYS = 7  # a Friday close still counts as the previous session after a long weekend
SESSION_LOOKBACK_DAYS = 10  # how far back the daily closes are read; covers a long weekend
MARKET_CLOSE = dt_time(15, 30)


def option_symbols_in(catalog_rows: list[dict]) -> list[str]:
    """Nifty option contracts with stored one-minute candles, from the Historify catalog."""
    return sorted(
        {
            str(row["symbol"])
            for row in catalog_rows
            if str(row.get("exchange", "")).upper() == OPTION_EXCHANGE
            and row.get("interval") == INTRADAY
            and OPTION_SYMBOL.match(str(row.get("symbol", "")))
        }
    )


def check_day(day: date, catalog_rows: list[dict], counts: dict) -> list[tuple[str, str]]:
    """Judge one trading day from plain data and say what is short, in words a trader can act on.

    ``catalog_rows`` are the Historify data-catalog rows. ``counts`` carries the numbers read from
    the database and the file system: ``option_candles`` (one-minute candle count per option
    symbol for the day), ``index_candles``, ``vix_days`` and ``etf_days`` (dates with a daily row,
    YYYY-MM-DD), ``before_close``, and ``artifacts`` (name, exists, age_hours, fix). Returns
    (level, message) pairs, level OK or PROBLEM.
    """
    findings: list[tuple[str, str]] = []
    index_candles = counts.get("index_candles", 0)
    if index_candles == 0 and day.weekday() >= 5:
        return [(OK, f"{day.isoformat()} was a weekend - no trading day, nothing to check.")]

    if not catalog_rows:
        return [
            (
                PROBLEM,
                "The candle store is empty - the evening capture has never run here. Run "
                "capture_option_candles.py after a trading day to start collecting.",
            )
        ]

    saved = counts.get("option_candles", {})
    symbols = option_symbols_in(catalog_rows)
    complete = [s for s in symbols if saved.get(s, 0) >= MIN_OPTION_CANDLES]
    partial = [s for s in symbols if 0 < saved.get(s, 0) < MIN_OPTION_CANDLES]
    absent = [s for s in symbols if saved.get(s, 0) == 0]
    if len(complete) >= MIN_OPTION_CONTRACTS:
        message = (
            f"{len(complete)} Nifty option contracts each have {MIN_OPTION_CANDLES}+ one-minute "
            f"candles for {day.isoformat()}."
        )
        findings.append((OK, message))
    else:
        gaps = []
        if absent:
            gaps.append(f"{len(absent)} saved no candle at all")
        if partial:
            gaps.append(f"{len(partial)} stopped short of {MIN_OPTION_CANDLES} candles")
        detail = "; ".join(gaps) if gaps else "the store has no candle for the rest"
        message = (
            f"Only {len(complete)} of the {MIN_OPTION_CONTRACTS} Nifty option contracts a full "
            f"day needs have a whole day of one-minute candles for {day.isoformat()} ({detail}). "
            "The 16:00 capture stopped early - run capture_option_candles.py again for that day."
        )
        examples = ", ".join((absent + partial)[:3])
        if examples:
            message += f" First to fix: {examples}."
        findings.append((PROBLEM, message))

    if index_candles >= MIN_INDEX_CANDLES:
        message = f"The Nifty index has {index_candles} one-minute candles for {day.isoformat()}."
        findings.append((OK, message))
    else:
        have = "no one-minute candle" if index_candles == 0 else f"only {index_candles}"
        message = (
            f"The Nifty index has {have} for {day.isoformat()} (a full session has "
            f"{FULL_SESSION_CANDLES}). If the exchange was closed that day this is fine; otherwise "
            "run capture_option_candles.py again - it also saves the index."
        )
        findings.append((PROBLEM, message))

    vix_days = sorted(counts.get("vix_days", []))
    previous = max((d for d in vix_days if d < day.isoformat()), default=None)
    if previous is not None and (day - date.fromisoformat(previous)).days <= VIX_MAX_GAP_DAYS:
        message = (
            f"India VIX has a daily close for the session before {day.isoformat()} ({previous})."
        )
        findings.append((OK, message))
    else:
        newest = f" - the newest close is {previous}" if previous else ""
        message = (
            f"India VIX has no daily close for the session before {day.isoformat()}{newest}. "
            "The forward tests read it - run capture_option_candles.py again; it also saves the "
            "VIX."
        )
        findings.append((PROBLEM, message))

    if counts.get("before_close"):
        earlier = [d for d in vix_days if d < day.isoformat()]
        latest = earlier[-1] if earlier else (day - timedelta(days=1)).isoformat()
        wanted = {day.isoformat(), latest}
    else:
        wanted = {day.isoformat()}
    etf_days = counts.get("etf_days", {})
    for symbol in ETF_SYMBOLS:
        have = set(etf_days.get(symbol, [])) & wanted
        if have:
            message = f"{symbol} has a daily close for {max(have)}."
            findings.append((OK, message))
        else:
            message = (
                f"{symbol} has no daily close for {day.isoformat()} yet. The ETF ledgers need it "
                "- run capture_option_candles.py again; it also saves the ETF closes."
            )
            findings.append((PROBLEM, message))

    for artifact in counts.get("artifacts", []):
        name = artifact.get("name", "a nightly report file")
        fix = artifact.get("fix", "run the nightly scripts")
        if not artifact.get("exists"):
            message = f"{name} is missing. {fix} so the next check has fresh data."
            findings.append((PROBLEM, message))
            continue
        age = artifact.get("age_hours")
        if age is None or age > MAX_ARTIFACT_AGE_HOURS:
            shown = "a long time" if age is None else f"{age:.0f} hours"
            message = (
                f"{name} was last updated {shown} ago, older than {MAX_ARTIFACT_AGE_HOURS} hours "
                f"- the nightly run that writes it did not happen. {fix}."
            )
            findings.append((PROBLEM, message))
        else:
            message = f"{name} is fresh (updated {age:.0f} hours ago)."
            findings.append((OK, message))
    return findings


def ist_day_bounds(day: date) -> tuple[int, int]:
    """Unix seconds (UTC) covering one India calendar day, the way get_ohlcv takes them."""
    start = int(datetime.combine(day, dt_time(0, 0), tzinfo=IST).timestamp())
    end = int(datetime.combine(day + timedelta(days=1), dt_time(0, 0), tzinfo=IST).timestamp())
    return start, end


def before_the_close(day: date, now: datetime | None = None) -> bool:
    """True when the run happens on ``day`` itself, before the NSE equity close."""
    moment = (now or datetime.now(IST)).astimezone(IST)
    return moment.date() == day and moment.time() < MARKET_CLOSE


def collect(day: date, before_close: bool) -> tuple[list[dict], dict]:
    """Read the catalog, the candle counts and the report file ages that check_day judges."""
    from database.historify_db import get_data_catalog, get_ohlcv

    start, end = ist_day_bounds(day)
    first_day = day - timedelta(days=SESSION_LOOKBACK_DAYS)
    window_start = int(datetime.combine(first_day, dt_time(0, 0), tzinfo=IST).timestamp())

    catalog_rows = get_data_catalog()

    option_candles: dict[str, int] = {}
    for symbol in option_symbols_in(catalog_rows):
        option_candles[symbol] = len(get_ohlcv(symbol, OPTION_EXCHANGE, INTRADAY, start, end))

    def daily_dates(symbol: str, exchange: str) -> list[str]:
        frame = get_ohlcv(symbol, exchange, DAILY, window_start, end)
        if frame is None or frame.empty:
            return []
        stamps = pd.to_datetime(frame["timestamp"], unit="s", utc=True).dt.tz_convert(
            "Asia/Kolkata"
        )
        return sorted(set(stamps.dt.strftime("%Y-%m-%d")))

    artifacts = []
    for name, path, fix in (
        (
            "db/forward_shadow/report.json",
            ROOT / "db" / "forward_shadow" / "report.json",
            "Run run_forward_shadow.py tonight",
        ),
        ("db/etf_ledger", ROOT / "db" / "etf_ledger", "Run run_etf_ledgers.py tonight"),
    ):
        exists = path.exists()
        age = (time.time() - path.stat().st_mtime) / 3600 if exists else None
        artifacts.append({"name": name, "exists": exists, "age_hours": age, "fix": fix})

    return catalog_rows, {
        "option_candles": option_candles,
        "index_candles": len(get_ohlcv(INDEX_SYMBOL, INDEX_EXCHANGE, INTRADAY, start, end)),
        "vix_days": daily_dates(VIX_SYMBOL, INDEX_EXCHANGE),
        "etf_days": {symbol: daily_dates(symbol, ETF_EXCHANGE) for symbol in ETF_SYMBOLS},
        "before_close": before_close,
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "day", nargs="?", default=None, help="day to check, YYYY-MM-DD (default: today in India)"
    )
    args = parser.parse_args()

    today = datetime.now(IST).date()
    day = today
    if args.day:
        try:
            day = date.fromisoformat(args.day)
        except ValueError:
            print(f"'{args.day}' is not a date in the YYYY-MM-DD shape, for example {today}.")
            return 2

    try:
        catalog_rows, counts = collect(day, before_the_close(day))
    except Exception:
        logger.exception("Could not read the stored candles")
        print(
            "Could not read the local candle store. Check that the Historify database is where it "
            "should be, then run capture_option_candles.py again."
        )
        return 2

    findings = check_day(day, catalog_rows, counts)
    print(f"Nightly data check for {day.isoformat()}:")
    for level, message in findings:
        print(f"  {level}: {message}")
    if any(level == PROBLEM for level, _ in findings):
        print("Fix the lines marked PROBLEM - until then this day's numbers cannot be trusted.")
        return 2
    print("Everything the forward tests need from this day is in place.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
