"""Read-only nightly forward ledger for the ATM 100 call credit spread."""

from __future__ import annotations

import argparse
import csv
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from services.algos import atm100_rule as rule
from services.algos import eod_screen, sandbox_bot
from services.algos.sandbox_bot_atm200 import expiry_window_ok, next_session

START = date(2026, 11, 26)
DATA_REPO = Path("D:/Github/openalgo-data")
IST = ZoneInfo("Asia/Kolkata")
CSV_COLUMNS = (
    "entry_date",
    "expiry",
    "spot",
    "sold",
    "long",
    "credit",
    "exit_time",
    "exit_value",
    "exit_reason",
    "gross",
    "cost",
    "net",
    "status",
    "note",
)

CandleReader = Callable[[str, str, str, int, int], pd.DataFrame]
HolidayChecker = Callable[[date, str], bool]


def ist_day_bounds(day: date) -> tuple[int, int]:
    """Return Unix seconds spanning an India calendar day."""
    start = int(datetime.combine(day, time.min, tzinfo=IST).timestamp())
    end = int(datetime.combine(day + timedelta(days=1), time.min, tzinfo=IST).timestamp())
    return start, end


def _next_trading_session(day: date, holiday_checker: HolidayChecker) -> date:
    holidays = {
        candidate
        for offset in range(1, 8)
        if holiday_checker(candidate := day + timedelta(days=offset), "NSE")
    }
    return next_session(day, holidays)


def _weekly_expiry(day: date, holiday_checker: HolidayChecker) -> date:
    """Find the upcoming Tuesday weekly expiry, shifted back across exchange holidays."""
    days_to_tuesday = (1 - day.weekday()) % 7 or 7
    expiry = day + timedelta(days=days_to_tuesday)
    while expiry.weekday() >= 5 or holiday_checker(expiry, "NSE"):
        expiry -= timedelta(days=1)
    return expiry


def _local_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty or "timestamp" not in frame:
        return pd.DataFrame()
    out = frame.copy()
    stamps = pd.to_datetime(out["timestamp"], unit="s", utc=True, errors="coerce")
    out["_local"] = stamps.dt.tz_convert(IST).dt.tz_localize(None)
    return out.dropna(subset=["_local"]).sort_values("_local")


def _at_time(frame: pd.DataFrame, day: date, clock: time) -> pd.Series | None:
    if frame.empty:
        return None
    match = frame[(frame["_local"].dt.date == day) & (frame["_local"].dt.time == clock)]
    return None if match.empty else match.iloc[-1]


def _option_symbol(expiry: date, strike: int) -> str:
    return sandbox_bot.contract_symbol(expiry, strike, "CE")


def _row(day: date, status: str, note: str, **values) -> dict:
    result = dict.fromkeys(CSV_COLUMNS, "")
    result.update(entry_date=day.isoformat(), status=status, note=note)
    result.update(values)
    return result


def build_ledger(
    start: date,
    through: date,
    candle_reader: CandleReader,
    holiday_checker: HolidayChecker,
    vix_reader: Callable[[date], float | None],
    cost_function: Callable = eod_screen.leg_cost,
    expiry_picker: Callable[[date, HolidayChecker], date] = _weekly_expiry,
) -> list[dict]:
    """Rebuild rows from synthetic or stored candles without network or broker access."""
    rows = []
    blocked_entry_days: set[date] = set()
    unresolved_position = False
    day = start
    while day <= through:
        if day.weekday() >= 5 or holiday_checker(day, "NSE"):
            day += timedelta(days=1)
            continue
        if unresolved_position or day in blocked_entry_days:
            rows.append(_row(day, "skipped", "The prior session's position was open at 10:15."))
            day += timedelta(days=1)
            continue
        next_day = _next_trading_session(day, holiday_checker)
        expiry = expiry_picker(day, holiday_checker)
        if not expiry_window_ok(
            day,
            expiry,
            {
                d
                for d in (day + timedelta(days=n) for n in range(1, 8))
                if holiday_checker(d, "NSE")
            },
        ):
            rows.append(_row(day, "skipped", "No eligible weekly expiry."))
            day += timedelta(days=1)
            continue

        entry_start, entry_end = ist_day_bounds(day)
        idx = _local_frame(candle_reader("NIFTY", "NSE_INDEX", "1m", entry_start, entry_end))
        entry_bar = _at_time(idx, day, time(10, 15))
        if entry_bar is None or pd.isna(entry_bar.get("close")):
            rows.append(_row(day, "no_data", "NIFTY 10:15 close is missing."))
            day += timedelta(days=1)
            continue
        spot = float(entry_bar["close"])
        sold_strike = rule.atm_strike(spot)
        sold_symbol = _option_symbol(expiry, sold_strike)
        long_symbol = _option_symbol(expiry, sold_strike + rule.WIDTH)
        sold_frame = _local_frame(candle_reader(sold_symbol, "NFO", "1m", entry_start, entry_end))
        long_frame = _local_frame(candle_reader(long_symbol, "NFO", "1m", entry_start, entry_end))
        sold_entry = _at_time(sold_frame, day, time(10, 15))
        long_entry = _at_time(long_frame, day, time(10, 15))
        if (
            sold_entry is None
            or long_entry is None
            or pd.isna(sold_entry.get("close"))
            or pd.isna(long_entry.get("close"))
        ):
            rows.append(_row(day, "no_data", "One or both option 10:15 closes are missing."))
            day += timedelta(days=1)
            continue

        plan = rule.plan_entry(
            spot, vix_reader(day), float(sold_entry["close"]), float(long_entry["close"])
        )
        if plan.skipped_reason:
            rows.append(
                _row(
                    day,
                    "skipped",
                    plan.skipped_reason,
                    expiry=expiry.isoformat(),
                    spot=spot,
                    sold=sold_symbol,
                    long=long_symbol,
                    credit=plan.credit_points,
                )
            )
            day += timedelta(days=1)
            continue

        exit_start = int(datetime.combine(day, time(10, 16), tzinfo=IST).timestamp())
        next_end = int(datetime.combine(next_day, time(15, 1), tzinfo=IST).timestamp())
        sold_path = _local_frame(candle_reader(sold_symbol, "NFO", "1m", exit_start, next_end))
        long_path = _local_frame(candle_reader(long_symbol, "NFO", "1m", exit_start, next_end))
        if (
            sold_path.empty
            or long_path.empty
            or "_local" not in sold_path
            or "_local" not in long_path
        ):
            path = pd.DataFrame()
        else:
            path = sold_path[["_local", "close"]].merge(
                long_path[["_local", "close"]],
                on="_local",
                suffixes=("_sold", "_long"),
                how="inner",
            )
            path = path[
                (path["_local"] > datetime.combine(day, time(10, 15)))
                & (path["_local"] <= datetime.combine(next_day, time(15, 0)))
            ].sort_values("_local")
        if path.empty:
            blocked_entry_days.add(
                next_day
            )  # unknown trade: no new entry until it would have ended
            rows.append(
                _row(
                    day,
                    "no_data",
                    "No option closes are available after entry.",
                    expiry=expiry.isoformat(),
                    spot=spot,
                    sold=sold_symbol,
                    long=long_symbol,
                    credit=plan.credit_points,
                )
            )
            day += timedelta(days=1)
            continue

        exit_value = None
        exit_reason = None
        exit_stamp = None
        time_bar = datetime.combine(next_day, time(15, 0))
        for _, candle in path.iterrows():
            value = float(candle["close_sold"] - candle["close_long"])
            is_time_bar = candle["_local"] == time_bar
            decision = rule.exit_decision(float(plan.credit_points), value, is_last_bar=is_time_bar)
            if decision:
                exit_value, exit_reason, exit_stamp = value, decision, candle["_local"]
                break

        if exit_reason is None:
            if through < next_day:
                unresolved_position = True
                rows.append(
                    _row(
                        day,
                        "open",
                        "Waiting for the next session 15:00 close.",
                        expiry=expiry.isoformat(),
                        spot=spot,
                        sold=sold_symbol,
                        long=long_symbol,
                        credit=plan.credit_points,
                    )
                )
                day += timedelta(days=1)
                continue
            if (
                _at_time(sold_path, next_day, time(15, 0)) is None
                or _at_time(long_path, next_day, time(15, 0)) is None
            ):
                blocked_entry_days.add(next_day)
                rows.append(
                    _row(
                        day,
                        "no_data",
                        "Next-session 15:00 option close is missing.",
                        expiry=expiry.isoformat(),
                        spot=spot,
                        sold=sold_symbol,
                        long=long_symbol,
                        credit=plan.credit_points,
                    )
                )
                day += timedelta(days=1)
                continue

        assert exit_value is not None and exit_reason is not None and exit_stamp is not None
        sold_exit_row = _at_time(sold_path, exit_stamp.date(), exit_stamp.time())
        long_exit_row = _at_time(long_path, exit_stamp.date(), exit_stamp.time())
        if sold_exit_row is None or long_exit_row is None:
            blocked_entry_days.add(next_day)
            rows.append(_row(day, "no_data", "An exit leg close is missing."))
            day += timedelta(days=1)
            continue
        sold_exit, long_exit = float(sold_exit_row["close"]), float(long_exit_row["close"])
        gross = rule.pnl_rupees(float(plan.credit_points), exit_value, rule.LOT)
        exit_day = exit_stamp.date()
        cost = cost_function(-1, float(sold_entry["close"]), sold_exit, day, exit_day, rule.LOT)
        cost += cost_function(1, float(long_entry["close"]), long_exit, day, exit_day, rule.LOT)
        rows.append(
            _row(
                day,
                "closed",
                "",
                expiry=expiry.isoformat(),
                spot=spot,
                sold=sold_symbol,
                long=long_symbol,
                credit=plan.credit_points,
                exit_time=exit_stamp.strftime("%Y-%m-%d %H:%M"),
                exit_value=exit_value,
                exit_reason=exit_reason,
                gross=gross,
                cost=cost,
                net=gross - cost,
            )
        )
        if exit_day == next_day and exit_stamp.time() >= time(10, 15):
            blocked_entry_days.add(next_day)  # still open at the next session's 10:15 entry
        day += timedelta(days=1)
    return rows


def read_previous_vix(path: Path) -> Callable[[date], float | None]:
    """Load daily VIX closes once and return only the latest strictly earlier date."""
    frame = pd.read_csv(path)
    date_column = next(
        (key for key in ("date", "timestamp", "Date", "Timestamp") if key in frame), None
    )
    close_column = next((key for key in ("close", "Close") if key in frame), None)
    if date_column is None or close_column is None:
        raise ValueError("India VIX file must contain date/timestamp and close columns")
    raw_dates = frame[date_column]
    if pd.api.types.is_numeric_dtype(raw_dates):
        parsed = pd.to_datetime(raw_dates, unit="s", utc=True, errors="coerce")
    else:
        parsed = pd.to_datetime(raw_dates, utc=True, errors="coerce")
    stamps = parsed.dt.tz_convert(IST).dt.tz_localize(None).dt.date
    values = {
        stamp: float(close)
        for stamp, close in zip(stamps, frame[close_column], strict=True)
        if not pd.isna(stamp) and not pd.isna(close)
    }

    def previous(day: date) -> float | None:
        prior = [stamp for stamp in values if stamp < day]
        return values[max(prior)] if prior else None

    return previous


def persist(rows: list[dict], path: Path, dry_run: bool = False) -> None:
    """Replace the deterministic ledger snapshot, or leave disk untouched for a dry run."""
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def summary(rows: list[dict]) -> dict:
    closed = [row for row in rows if row["status"] == "closed"]
    return {
        "closed": len(closed),
        "open": sum(row["status"] == "open" for row in rows),
        "net": sum(float(row["net"]) for row in closed),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-repo", type=Path, default=DATA_REPO)
    parser.add_argument(
        "--dry-run", action="store_true", help="build and summarize without writing the ledger"
    )
    args = parser.parse_args(argv)

    from database import historify_db, market_calendar_db

    today = datetime.now(IST).date()
    rows = build_ledger(
        START,
        today,
        historify_db.get_ohlcv,
        market_calendar_db.is_market_holiday,
        read_previous_vix(args.data_repo / "context" / "daily" / "_INDIAVIX.csv"),
    )
    path = args.data_repo / "research" / "atm100_forward" / "ledger.csv"
    persist(rows, path, args.dry_run)
    result = summary(rows)
    print(
        f"closed={result['closed']} open={result['open']} net={result['net']:.2f} "
        f"toward_60={result['closed']}/60"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
