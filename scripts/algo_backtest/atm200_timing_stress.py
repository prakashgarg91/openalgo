"""Measure pre-registered timing variants of the frozen ATM 200 replay (read only)."""

import csv
import importlib.util
import io
import sys
import tarfile
from pathlib import Path

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from services.algos import atm200_rule as rule  # noqa: E402
from services.algos import eod_screen as es  # noqa: E402
from services.algos import nse_lots  # noqa: E402

DATA_REPO = Path("D:/Github/openalgo-data")
REPLAY_FILE = Path("D:/Github/openalgo-cloud/scripts/algo_backtest/zen_structure_replay.py")
_spec = importlib.util.spec_from_file_location("zen_structure_replay", REPLAY_FILE)
zsr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(zsr)

VARIANTS = ("base", "a_entry_open", "b_entry_next", "c_intrabar_stop", "d_exit_next_bar", "e_all")
BASE_EXPECTED = (388, 171325, 110290)


def load_expiry(repo: Path, expiry: str) -> dict[tuple[str, int], pd.DataFrame]:
    """Load the OHLC candles required for timing fills from the frozen data archive."""
    out = {}
    with tarfile.open(repo / "bars5m" / f"{expiry}.tar.gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            _, kind, strike = Path(member.name).stem.split("_")
            stream = tar.extractfile(member)
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
    """Replay a single already-selected trade; exposed for deterministic synthetic tests."""
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
        # A spread of calls this wide can never cost more than its width, so the fill is capped there.
        stop_fill = min(
            float(rule.WIDTH), max(rule.STOP * credit, float(row.open_sold - row.open_long))
        )
        exit_value = stop_fill
        long_exit = float(row.open_long)
        sold_exit = long_exit + stop_fill
        stopped_intrabar = True
    # An intrabar stop is filled inside its own bar, so the next-bar rule applies only to exits decided on a close.
    if next_exit and not stopped_intrabar and chosen < len(path) - 1:
        chosen += 1
        row = path.iloc[chosen]
        sold_exit, long_exit = float(row.close_sold), float(row.close_long)
        exit_value, why = sold_exit - long_exit, why
    if variant != "base":  # the base stays byte-for-byte the frozen replay
        exit_value = min(
            float(rule.WIDTH), max(0.0, exit_value)
        )  # a spread lies between 0 and its width
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


def run(repo: Path) -> dict[str, pd.DataFrame]:
    with (repo / "MANIFEST.csv").open(encoding="utf-8") as fh:
        expiries = sorted(pd.Timestamp(row["expiry"]) for row in csv.DictReader(fh))
    idx = (
        pd.read_csv(repo / "index" / "nifty_1m.csv", parse_dates=["timestamp"])
        .set_index("timestamp")
        .sort_index()["close"]
    )
    vix = zsr.daily(repo, "_INDIAVIX.csv")
    sessions = sorted(set(idx.index.normalize()))
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
            t0 = day + entry_offset
            if t0 not in idx.index:
                continue
            prev = [session for session in sessions if session < day]
            vix_prev = vix.get(prev[-1]) if prev else None
            sold_strike = rule.atm_strike(float(idx.loc[t0]))
            sold, long_ = data.get(("CE", sold_strike)), data.get(("CE", sold_strike + rule.WIDTH))
            if sold is None or long_ is None or t0 not in sold.index or t0 not in long_.index:
                continue
            plan = rule.plan_entry(
                float(idx.loc[t0]),
                vix_prev,
                float(sold.loc[t0, "close"]),
                float(long_.loc[t0, "close"]),
            )
            if (
                plan.skipped_reason is not None
                or plan.sold_strike != sold_strike
                or plan.bought_strike != sold_strike + rule.WIDTH
            ):
                continue
            end_ts = next_day + exit_offset
            for name in VARIANTS:
                trade = replay_trade(sold, long_, t0, end_ts, float(plan.credit_points), name, lot)
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
                        "vix_prev": vix_prev,
                    }
                )
    return {name: pd.DataFrame(rows) for name, rows in output.items()}


def summarize(frame: pd.DataFrame) -> dict:
    net = frame["net"]
    n = len(frame)
    sd = float(net.std(ddof=1))
    ordered = frame.sort_values("date")
    return {
        "trades": n,
        "realistic": round(float(net.sum())),
        "doubled": round(float(frame["net2x"].sum())),
        "mean": float(net.mean()),
        "t": float(net.mean()) / sd * np.sqrt(n) if sd else float("nan"),
        "worst": round(float(net.min())),
        "dd": zsr.stats(ordered)["dd"],
    }


def main() -> int:
    frames = run(DATA_REPO)
    base = summarize(frames["base"])
    if (base["trades"], base["realistic"], base["doubled"]) != BASE_EXPECTED:
        print(f"BASE MISMATCH: {base}; expected trades/net/net2x={BASE_EXPECTED}")
        return 1
    base_net = base["realistic"]
    for name, frame in frames.items():
        result = summarize(frame)
        print(
            f"{name}: trades={result['trades']} net_realistic={result['realistic']} "
            f"net_doubled={result['doubled']} mean={result['mean']:.2f} t={result['t']:.3f} "
            f"worst={result['worst']} deepest_fall={result['dd']} "
            f"change_vs_base={result['realistic'] - base_net}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
