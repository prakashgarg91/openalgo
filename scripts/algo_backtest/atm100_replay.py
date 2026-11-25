"""One-time descriptive timing replay of the pre-registered ATM 100 spread."""

from __future__ import annotations

import csv
import io
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd

from services.algos import atm100_rule as rule
from services.algos import eod_screen as es
from services.algos import nse_lots

DATA_REPO = Path("D:/Github/openalgo-data")
VARIANTS = ("base", "a_entry_open", "b_entry_next", "c_intrabar_stop", "d_exit_next_bar", "e_all")


def load_expiry(repo: Path, expiry: str) -> dict[tuple[str, int], pd.DataFrame]:
    """Load just the archived option bars used for the timing fills."""
    out = {}
    with tarfile.open(repo / "bars5m" / f"{expiry}.tar.gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            _, kind, strike = Path(member.name).stem.split("_")
            stream = archive.extractfile(member)
            if stream is None:
                continue
            frame = pd.read_csv(io.BytesIO(stream.read()), parse_dates=["timestamp"])
            out[(kind, int(float(strike)))] = frame.set_index("timestamp")[
                ["open", "high", "low", "close"]
            ].sort_index()
    return out


def replay_trade(
    sold: pd.DataFrame,
    long_: pd.DataFrame,
    entry_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    gate_credit: float,
    variant: str,
    lot: int = rule.LOT,
) -> dict | None:
    """Replay one selected trade using the frozen ATM 200 timing logic and ATM 100 rules."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant: {variant}")
    use_next_entry = variant in ("b_entry_next", "e_all")
    intrabar = variant in ("c_intrabar_stop", "e_all")
    next_exit = variant in ("d_exit_next_bar", "e_all")
    use_open = variant == "a_entry_open"
    if entry_ts not in sold.index or entry_ts not in long_.index:
        return None
    entry_index = sold.index.get_loc(entry_ts)
    fill_index = entry_index + 1 if use_next_entry else entry_index
    if fill_index >= len(sold.index):
        return None
    fill_ts = sold.index[fill_index]
    if fill_ts not in long_.index:
        return None
    entry_col = "open" if use_open else "close"
    if use_next_entry:
        entry_col = "close"
    sold_entry = float(sold.loc[fill_ts, entry_col])
    long_entry = float(long_.loc[fill_ts, entry_col])
    credit = sold_entry - long_entry
    if gate_credit <= rule.MIN_CREDIT_POINTS or credit <= 0:
        return None
    aligned = sold.join(long_, lsuffix="_sold", rsuffix="_long", how="inner")
    path = aligned.loc[(aligned.index > fill_ts) & (aligned.index <= end_ts)]
    if path.empty:
        return None
    exit_value = float(path.iloc[-1].close_sold - path.iloc[-1].close_long)
    why, chosen = "time", len(path) - 1
    for i, row in enumerate(path.itertuples()):
        value = float(row.close_sold - row.close_long)
        reason = rule.exit_decision(credit, value, is_last_bar=(i == len(path) - 1))
        if intrabar and float(row.high_sold - row.low_long) >= rule.STOP * credit:
            reason = "stop"
        if reason is not None:
            exit_value, why, chosen = value, reason, i
            break
    row = path.iloc[chosen]
    sold_exit, long_exit = float(row.close_sold), float(row.close_long)
    stopped_intrabar = False
    if intrabar and why == "stop":
        stop_fill = min(
            float(rule.WIDTH), max(rule.STOP * credit, float(row.open_sold - row.open_long))
        )
        exit_value = stop_fill
        long_exit = float(row.open_long)
        sold_exit = long_exit + stop_fill
        stopped_intrabar = True
    if next_exit and not stopped_intrabar and chosen < len(path) - 1:
        chosen += 1
        row = path.iloc[chosen]
        sold_exit, long_exit = float(row.close_sold), float(row.close_long)
        exit_value, why = sold_exit - long_exit, why
    if variant != "base":
        exit_value = min(float(rule.WIDTH), max(0.0, exit_value))
    gross = rule.pnl_rupees(credit, exit_value, lot)
    return {
        "credit": credit,
        "exit": exit_value,
        "why": why,
        "sold_entry": sold_entry,
        "long_entry": long_entry,
        "sold_exit": sold_exit,
        "long_exit": long_exit,
        "exit_ts": path.index[chosen],
        "gross": gross,
    }


def _daily_vix(repo: Path) -> dict[pd.Timestamp, float]:
    frame = pd.read_csv(repo / "context" / "daily" / "_INDIAVIX.csv")
    date_column = next(
        (name for name in ("date", "timestamp", "Date", "Timestamp") if name in frame), None
    )
    close_column = next((name for name in ("close", "Close") if name in frame), None)
    if date_column is None or close_column is None:
        raise ValueError("India VIX file must contain date/timestamp and close columns")
    raw_dates = frame[date_column]
    if pd.api.types.is_numeric_dtype(raw_dates):
        stamps = pd.to_datetime(raw_dates, unit="s", utc=True, errors="coerce")
    else:
        stamps = pd.to_datetime(raw_dates, utc=True, errors="coerce")
    dates = stamps.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None).dt.normalize()
    return {
        pd.Timestamp(day): float(value)
        for day, value in zip(dates, frame[close_column], strict=True)
        if not pd.isna(day) and not pd.isna(value)
    }


def run(repo: Path) -> dict[str, pd.DataFrame]:
    """Run the six fixed variants once over the archived data."""
    with (repo / "MANIFEST.csv").open(encoding="utf-8") as handle:
        expiries = sorted(pd.Timestamp(row["expiry"]) for row in csv.DictReader(handle))
    index = pd.read_csv(repo / "index" / "nifty_1m.csv", parse_dates=["timestamp"])
    nifty = index.set_index("timestamp").sort_index()["close"]
    vix = _daily_vix(repo)
    sessions = sorted(set(nifty.index.normalize()))
    entry_offset = pd.Timedelta(hours=10, minutes=15)
    exit_offset = pd.Timedelta(hours=15)
    output = {name: [] for name in VARIANTS}
    for expiry in expiries:
        data = load_expiry(repo, expiry.strftime("%Y-%m-%d"))
        lot = nse_lots.nifty_lot(expiry)
        if lot is None:
            continue
        for day in sessions:
            if not (0 < (expiry - day).days <= rule.MAX_DAYS_TO_EXPIRY):
                continue
            later = [session for session in sessions if session > day]
            if not later or later[0] > expiry:
                continue
            next_day = later[0]
            entry_ts = day + entry_offset
            if entry_ts not in nifty.index:
                continue
            previous = [session for session in sessions if session < day]
            vix_prev = vix.get(previous[-1]) if previous else None
            sold_strike = rule.atm_strike(float(nifty.loc[entry_ts]))
            sold = data.get(("CE", sold_strike))
            long_ = data.get(("CE", sold_strike + rule.WIDTH))
            if (
                sold is None
                or long_ is None
                or entry_ts not in sold.index
                or entry_ts not in long_.index
            ):
                continue
            plan = rule.plan_entry(
                float(nifty.loc[entry_ts]),
                vix_prev,
                float(sold.loc[entry_ts, "close"]),
                float(long_.loc[entry_ts, "close"]),
            )
            if plan.skipped_reason is not None:
                continue
            end_ts = next_day + exit_offset
            for name in VARIANTS:
                trade = replay_trade(
                    sold, long_, entry_ts, end_ts, float(plan.credit_points), name, lot
                )
                if trade is None:
                    continue
                cost = es.leg_cost(-1, trade["sold_entry"], trade["sold_exit"], day, next_day, lot)
                cost += es.leg_cost(1, trade["long_entry"], trade["long_exit"], day, next_day, lot)
                output[name].append(
                    {
                        "date": day,
                        "expiry": expiry,
                        "credit": trade["credit"],
                        "exit": trade["exit"],
                        "why": trade["why"],
                        "gross": trade["gross"],
                        "cost": cost,
                        "net": trade["gross"] - cost,
                        "net2x": trade["gross"] - 2 * cost,
                    }
                )
    return {name: pd.DataFrame(rows) for name, rows in output.items()}


def summarize(frame: pd.DataFrame) -> dict:
    net = frame["net"]
    count = len(frame)
    deviation = float(net.std(ddof=1))
    ordered = frame.sort_values("date")
    equity = np.r_[0.0, ordered["net"].cumsum().to_numpy()]
    drawdown = float((np.maximum.accumulate(equity) - equity).max()) if len(equity) else 0.0
    return {
        "trades": count,
        "realistic": round(float(net.sum())),
        "doubled": round(float(frame["net2x"].sum())),
        "mean": float(net.mean()),
        "t": float(net.mean()) / deviation * np.sqrt(count) if deviation else float("nan"),
        "worst": round(float(net.min())),
        "dd": round(drawdown),
    }


def main() -> int:
    """Print the six registered timing summaries; this is never run by the tests."""
    frames = run(DATA_REPO)
    base_net = summarize(frames["base"])["realistic"]
    for name in VARIANTS:
        result = summarize(frames[name])
        print(
            f"{name}: trades={result['trades']} net_realistic={result['realistic']} "
            f"net_doubled={result['doubled']} mean={result['mean']:.2f} t={result['t']:.3f} "
            f"worst={result['worst']} deepest_fall={result['dd']} "
            f"change_vs_base={result['realistic'] - base_net}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
