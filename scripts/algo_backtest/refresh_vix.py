"""Add the newest India VIX daily bars to <data_repo>/context/daily/_INDIAVIX.csv.

fetch_context_data.py rewrites every file, so it is not reused here. This script only appends the
sessions after the last stored date, so the file grows and never shrinks. A bar for today is
dropped until the India session has closed (15:45 IST), so a half-formed bar never becomes the
previous close. The write goes to a temp file first and then replaces the stored file.

Usage:
    uv run python scripts/algo_backtest/refresh_vix.py <data_repo> [--dry-run]

Exit code 0 means the file is current. 1 means the Yahoo fetch failed, or the last stored date is
more than 4 calendar days behind today (the stored file is left as it was when the fetch fails).
"""

import argparse
import os
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from fetch_context_data import HEADERS, fetch  # noqa: E402

from utils.logging import get_logger  # noqa: E402

logger = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")
SYMBOL = "^INDIAVIX"
INTERVAL = "1d"
FILE_NAME = "_INDIAVIX.csv"
INDEX_NAME = "timestamp_utc"
SESSION_CLOSE = time(15, 45)
MAX_BEHIND_DAYS = 4


def _as_utc_index(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame indexed by UTC timestamps (strings from a CSV are parsed here)."""
    if frame.empty:
        return pd.DataFrame(
            columns=list(frame.columns), index=pd.DatetimeIndex([], tz="UTC", name=INDEX_NAME)
        )
    out = frame.copy()
    out.index = pd.DatetimeIndex(pd.to_datetime(out.index, utc=True), name=INDEX_NAME)
    return out


def _session_dates(index: pd.DatetimeIndex) -> list[date]:
    """The India calendar date of each UTC timestamp."""
    return [stamp.date() for stamp in index.tz_convert(IST)]


def _completed_mask(index: pd.DatetimeIndex, now_ist: datetime) -> pd.Series:
    """True for every bar whose India session has closed by ``now_ist``."""
    now = now_ist.astimezone(IST)
    closed_today = now.time() >= SESSION_CLOSE
    flags = [
        day < now.date() or (day == now.date() and closed_today) for day in _session_dates(index)
    ]
    return pd.Series(flags, index=index, dtype=bool)


def merge_vix(old_df: pd.DataFrame, new_df: pd.DataFrame, now_ist: datetime) -> pd.DataFrame:
    """Stored bars plus the completed new bars that fall after the last stored date.

    Stored rows always win: a new bar is only added when its India date is later than the last
    stored date. Bars for today are dropped before the session closes. The result never has fewer
    rows than ``old_df``.
    """
    old = _as_utc_index(old_df)
    new = _as_utc_index(new_df)
    if not new.empty:
        new = new.loc[_completed_mask(new.index, now_ist)]
    if old.empty:
        merged = new
    else:
        last_stored = max(_session_dates(old.index))
        if not new.empty:
            after = pd.Series([d > last_stored for d in _session_dates(new.index)], index=new.index)
            new = new.loc[after.astype(bool)]
        merged = pd.concat([old, new]) if not new.empty else old
        merged = merged[~merged.index.duplicated(keep="first")]
    merged = merged.sort_index()
    if len(merged) < len(old):
        return old.sort_index()
    merged.index.name = INDEX_NAME
    return merged


def staleness(df: pd.DataFrame, today: date) -> int | None:
    """Calendar days from the last stored session to ``today``, or None when nothing is stored."""
    if df is None or df.empty:
        return None
    last = max(_session_dates(_as_utc_index(df).index))
    return (today - last).days


def read_stored(path: Path) -> pd.DataFrame:
    """The stored CSV, or an empty frame when the file is missing or zero bytes."""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, index_col=INDEX_NAME)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def write_atomic(frame: pd.DataFrame, path: Path) -> None:
    """Write beside the target, then replace it in one step."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    frame.to_csv(tmp, float_format="%.6g")
    os.replace(tmp, path)


def refresh(data_repo: Path, client: httpx.Client, now_ist: datetime, dry_run: bool) -> int:
    """Fetch, merge, write and report. Returns the exit code (0 current, 1 problem)."""
    path = data_repo / "context" / "daily" / FILE_NAME
    old = read_stored(path)
    old_rows = len(_as_utc_index(old))
    today = now_ist.astimezone(IST).date()

    new = fetch(client, SYMBOL, INTERVAL, None)
    if new.empty:
        print(f"Could not fetch {SYMBOL} from Yahoo. The stored file was left as it was.")
        last = max(_session_dates(_as_utc_index(old).index)) if old_rows else None
        print(f"Last stored date: {last.isoformat() if last else 'none'}")
        print(f"WARNING: {SYMBOL} is not refreshed. Run it again later.")
        return 1

    merged = merge_vix(old, new, now_ist)
    if len(merged) < old_rows:
        print("Refusing to write: the merged series would be shorter than the stored one.")
        return 1
    added = len(merged) - old_rows
    last = max(_session_dates(merged.index)) if len(merged) else None

    if added and not dry_run:
        write_atomic(merged, path)
    verb = "Would add" if dry_run else "Added"
    print(f"{verb} {added} rows to {path.name}. Last date: {last.isoformat() if last else 'none'}")

    behind = staleness(merged, today)
    if behind is None or behind > MAX_BEHIND_DAYS:
        shown = "no stored data" if behind is None else f"{behind} calendar days"
        print(f"WARNING: {SYMBOL} is {shown} behind {today.isoformat()}. Check the feed.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_repo", type=Path, help="path to the openalgo-data repository")
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args(argv)
    if not args.data_repo.is_dir():
        print(f"'{args.data_repo}' is not a folder. Pass the openalgo-data repository path.")
        return 1
    try:
        with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
            return refresh(args.data_repo, client, datetime.now(IST), args.dry_run)
    except Exception:
        logger.exception("VIX refresh failed")
        print("VIX refresh failed unexpectedly. Details are in log/errors.jsonl.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
