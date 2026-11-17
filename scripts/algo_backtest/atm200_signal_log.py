"""Exploratory signal log for the frozen ATM 200-point call credit spread rule.

For each entry date that has a 10:15 snapshot, this works out what services/algos/atm200_rule.py
would have done that day, then follows the position through the later stored snapshots. It is a
log, not a test: it counts toward no registered result, places no order and never calls a broker.
Every price comes from the stored bid-ask CSVs in the data repository.

Usage:
    uv run python scripts/algo_backtest/atm200_signal_log.py <data_repo> [--dry-run]

Without --dry-run the rows are written to <data_repo>/recorder/atm200_signal_log.csv, updated by
entry date. --dry-run prints the computed rows and writes nothing.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.algos import atm200_rule as rule  # noqa: E402

NOTE = "exploratory log, not a test"
LOG_NAME = "atm200_signal_log.csv"
VIX_PATH = ("context", "daily", "_INDIAVIX.csv")
IST = timezone(timedelta(hours=5, minutes=30))  # India has no daylight saving time
LABELS = ("1015", "1430", "1500")
ENTRY_LABEL = "1015"
STALE_VIX_DAYS = 5  # an older previous VIX close is not used for the gate
NEXT_SESSION_MAX_DAYS = 4  # the next dated file counts only this close to the entry
NOTE_STALE_VIX = "VIX series is stale: gate not applied."
NOTE_NO_NEXT = "No next-session snapshot yet."
REASON_EXPIRY_WINDOW = "The nearest expiry is not one to six days away."
COLUMNS = [
    "entry_date",
    "expiry",
    "spot",
    "sold_strike",
    "bought_strike",
    "vix_prev",
    "credit_points",
    "skipped_reason",
    "status",
    "exit_reason",
    "exit_stamp",
    "exit_value_points",
    "gross_rupees",
    "note",
]
_MONTHS = {
    name: number
    for number, name in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
        start=1,
    )
}


def _number(text: str | None) -> float | None:
    """A float from a CSV cell, or None when the cell is blank, not a number, or NaN."""
    if text is None or not text.strip():
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return None if math.isnan(value) else value


def parse_expiry(text: str) -> date:
    """Parse an expiry such as 17-NOV-26 without depending on the process locale."""
    day, month, year = text.strip().upper().split("-")
    return date(2000 + int(year), _MONTHS[month], int(day))


def ist_date(timestamp_utc: str) -> date:
    """The Asia/Kolkata calendar date of a UTC timestamp, as the replay's daily() computes it."""
    return datetime.fromisoformat(timestamp_utc.strip()).astimezone(IST).date()


def parse_vix_closes(csv_text: str) -> dict[date, float]:
    """India VIX closes keyed by IST date. A later duplicate date wins, as in the replay."""
    closes: dict[date, float] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        close = _number(row.get("close"))
        if close is not None:
            closes[ist_date(row["timestamp_utc"])] = close
    return closes


def previous_vix(closes: dict[date, float], entry: date) -> tuple[date, float] | None:
    """The previous session's VIX close as (its date, close): the latest close strictly before
    the entry date, or None when the series has none."""
    earlier = [day for day in closes if day < entry]
    if not earlier:
        return None
    day = max(earlier)
    return day, closes[day]


def next_session(
    entry: date, expiry: date, snaps: dict[date, dict[str, list[dict]]]
) -> date | None:
    """The next dated file, but only when it is at most NEXT_SESSION_MAX_DAYS after the entry and
    holds the same expiry. Otherwise None: there is no next session to follow yet."""
    following = [day for day in snaps if day > entry]
    if not following:
        return None
    nxt = min(following)
    if (nxt - entry).days > NEXT_SESSION_MAX_DAYS:
        return None
    holds_expiry = any(r["expiry"] == expiry for rows in snaps[nxt].values() for r in rows)
    return nxt if holds_expiry else None


def parse_snapshot(csv_text: str) -> dict[str, list[dict]]:
    """One day's bid-ask file, grouped by label. Prices are floats and expiry is a date."""
    by_label: dict[str, list[dict]] = {}
    for raw in csv.DictReader(io.StringIO(csv_text)):
        try:
            row = {
                "stamp": raw["stamp"].strip(),
                "label": raw["label"].strip(),
                "expiry": parse_expiry(raw["expiry"]),
                "kind": raw["kind"].strip().upper(),
                "strike": int(float(raw["strike"])),
                "spot": _number(raw.get("spot")),
                "bid": _number(raw.get("bid")),
                "ask": _number(raw.get("ask")),
            }
        except (KeyError, ValueError):
            continue
        by_label.setdefault(row["label"], []).append(row)
    return by_label


def read_snapshots(bidask_dir: Path) -> dict[date, dict[str, list[dict]]]:
    """Every dated bid-ask file under the folder, keyed by the date in its file name."""
    snaps: dict[date, dict[str, list[dict]]] = {}
    for path in sorted(bidask_dir.glob("*.csv")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        snaps[day] = parse_snapshot(path.read_text(encoding="utf-8"))
    return snaps


def ce_by_strike(rows: list[dict], expiry: date) -> dict[int, dict]:
    """The call rows of one expiry, keyed by strike."""
    return {r["strike"]: r for r in rows if r["kind"] == "CE" and r["expiry"] == expiry}


def later_marks(
    entry: date, next_day: date | None, snaps: dict[date, dict[str, list[dict]]]
) -> list[tuple[date, str]]:
    """Snapshots after the 10:15 entry, in time order: the same day's 14:30 and 15:00, then the
    next session's 10:15, 14:30 and 15:00 when there is a valid next session."""
    marks = [(entry, label) for label in ("1430", "1500") if label in snaps[entry]]
    if next_day is not None:
        marks += [(next_day, label) for label in LABELS if label in snaps[next_day]]
    return marks


def follow_position(
    entry: date,
    expiry: date,
    sold_strike: int,
    bought_strike: int,
    credit: float,
    snaps: dict[date, dict[str, list[dict]]],
    next_day: date | None,
) -> tuple[str, str, str, float | None]:
    """Walk the later marks and return (status, exit_reason, exit_stamp, exit_value_points).

    A mark costs the sold call's ask minus the bought call's bid. Only the valid next session's
    15:00 mark is the last bar. A mark with a missing price is skipped. No decision means open.
    """
    for day, label in later_marks(entry, next_day, snaps):
        ce = ce_by_strike(snaps[day].get(label, []), expiry)
        sold = ce.get(sold_strike)
        bought = ce.get(bought_strike)
        if sold is None or bought is None or sold["ask"] is None or bought["bid"] is None:
            continue
        cost = sold["ask"] - bought["bid"]
        is_last = day == next_day and label == "1500"
        reason = rule.exit_decision(credit, cost, is_last)
        if reason is not None:
            return "closed", reason, sold["stamp"], cost
    return "open", "", "", None


def _fmt(value: float | None, places: int = 2) -> str:
    return "" if value is None else f"{value:.{places}f}"


def _entry_log(
    entry: date,
    entry_rows: list[dict],
    snaps: dict[date, dict[str, list[dict]]],
    closes: dict[date, float],
) -> dict[str, str]:
    spot = next((r["spot"] for r in entry_rows if r["spot"] is not None), None)
    expiry = min(r["expiry"] for r in entry_rows)
    ce = ce_by_strike(entry_rows, expiry)
    notes: list[str] = []
    found = previous_vix(closes, entry)
    prev = found[1] if found else None
    if found is not None and (entry - found[0]).days > STALE_VIX_DAYS:
        prev = None  # a stale close is not a gate: treat as missing
        notes.append(NOTE_STALE_VIX)
    atm = rule.atm_strike(spot) if spot is not None else None
    sold = ce.get(atm) if atm is not None else None
    bought = ce.get(atm + rule.WIDTH) if atm is not None else None
    plan = rule.plan_entry(
        spot,
        prev,
        sold["bid"] if sold else None,
        bought["ask"] if bought else None,
    )
    days_to_expiry = (expiry - entry).days
    window_ok = 1 <= days_to_expiry <= rule.MAX_DAYS_TO_EXPIRY
    skipped_reason = plan.skipped_reason if window_ok else REASON_EXPIRY_WINDOW
    row = dict.fromkeys(COLUMNS, "")
    row.update(
        entry_date=entry.isoformat(),
        expiry=expiry.isoformat(),
        spot=_fmt(spot),
        sold_strike="" if plan.sold_strike is None else str(plan.sold_strike),
        bought_strike="" if plan.bought_strike is None else str(plan.bought_strike),
        vix_prev=_fmt(prev),
        credit_points=_fmt(plan.credit_points),
        skipped_reason=skipped_reason or "",
    )
    if skipped_reason is not None:
        row["status"] = "skipped"
        row["note"] = " ".join(notes) or NOTE
        return row
    next_day = next_session(entry, expiry, snaps)
    status, reason, stamp, exit_value = follow_position(
        entry, expiry, plan.sold_strike, plan.bought_strike, plan.credit_points, snaps, next_day
    )
    if status == "open" and next_day is None:
        notes.append(NOTE_NO_NEXT)
    row["note"] = " ".join(notes) or NOTE
    row["status"] = status
    if status == "closed":
        row.update(
            exit_reason=reason,
            exit_stamp=stamp,
            exit_value_points=_fmt(exit_value),
            gross_rupees=_fmt(rule.pnl_rupees(plan.credit_points, exit_value)),
        )
    return row


def build_log(
    snaps: dict[date, dict[str, list[dict]]], closes: dict[date, float]
) -> list[dict[str, str]]:
    """One log row for every dated file that has a 10:15 snapshot, in date order."""
    rows = []
    for entry in sorted(snaps):
        entry_rows = snaps[entry].get(ENTRY_LABEL)
        if entry_rows:
            rows.append(_entry_log(entry, entry_rows, snaps, closes))
    return rows


def merge_rows(existing: list[dict], new: list[dict]) -> list[dict]:
    """Existing rows with the same entry date replaced by the new ones, sorted by entry date."""
    by_date = {row["entry_date"]: row for row in existing}
    by_date.update({row["entry_date"]: row for row in new})
    return [by_date[key] for key in sorted(by_date)]


def read_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_log(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exploratory ATM 200 signal log (not a test).")
    parser.add_argument("data_repo", type=Path, help="path to the openalgo-data repository")
    parser.add_argument("--dry-run", action="store_true", help="print the rows, write nothing")
    args = parser.parse_args(argv)

    bidask_dir = args.data_repo / "bidask"
    if not bidask_dir.is_dir():
        print(f"no bidask folder under {args.data_repo}", file=sys.stderr)
        return 2
    snaps = read_snapshots(bidask_dir)
    vix_file = args.data_repo.joinpath(*VIX_PATH)
    closes = parse_vix_closes(vix_file.read_text(encoding="utf-8")) if vix_file.is_file() else {}
    new_rows = build_log(snaps, closes)

    if args.dry_run:
        writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(new_rows)
        print(f"dry run: {len(new_rows)} rows computed, nothing written")
        return 0

    log_path = args.data_repo / "recorder" / LOG_NAME
    merged = merge_rows(read_log(log_path), new_rows)
    write_log(log_path, merged)
    print(f"wrote {len(merged)} rows to {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
