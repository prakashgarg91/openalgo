"""The ATM 200 spread replayed without its two gates, against the gated rule (read only).

The gated rule (services/algos/atm200_rule.py, plan_entry) refuses a day when the previous
session's India VIX close is 20 or higher, and refuses it again when the 10:15 credit is 5
points or less. This study replays the identical spread with both filters removed: every
eligible day -- same expiry window (at most 6 calendar days to the nearest expiry), same
strikes (ATM and ATM + 200), same 10:15 entry, same target, stop and 15:00 time exit, same
lots by expiry from services/algos/nse_lots.py -- is entered unless a price is missing.

run_ungated below is atm200_timing_stress.run with the plan_entry call replaced by the day's
own numbers, and replay_trade_ungated is that module's replay_trade minus the credit-floor
clause in its entry guard. Everything else is kept identical, so the gate-open days must
reproduce the frozen gated replay exactly; main() verifies that against the stress module's
own BASE_EXPECTED check and against its run() output before printing anything.

For each of the base and e_all timings (as defined in atm200_timing_stress.py, with its
width cap and intrabar-stop handling) the report prints the gated summary, the ungated
summary, and the ungated trades the gate would have skipped on their own.

A counted trial: this script is run once, after review, on the frozen data repo.
"""

import csv
import sys
from pathlib import Path

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from scripts.algo_backtest import atm200_timing_stress as stress  # noqa: E402
from services.algos import atm200_rule as rule  # noqa: E402
from services.algos import eod_screen as es  # noqa: E402
from services.algos import nse_lots  # noqa: E402

DATA_REPO = stress.DATA_REPO
VARIANTS = ("base", "e_all")


def replay_trade_ungated(
    sold: pd.DataFrame,
    long_: pd.DataFrame,
    entry_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    variant: str,
    lot: int = rule.LOT,
) -> dict | None:
    """The stress replay_trade without the plan's credit floor: the entry guard keeps only the
    non-positive-fill-credit refusal (unusable prices). Everything else is copied unchanged."""
    if variant not in stress.VARIANTS:
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
    if credit <= 0:
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


def run_ungated(repo: Path) -> dict[str, pd.DataFrame]:
    """The stress run() loop with the two plan_entry filters removed: a day is skipped only
    when its 10:15 prices are missing. Everything else mirrors the stress loop line for line."""
    with (repo / "MANIFEST.csv").open(encoding="utf-8") as fh:
        expiries = sorted(pd.Timestamp(row["expiry"]) for row in csv.DictReader(fh))
    idx = (
        pd.read_csv(repo / "index" / "nifty_1m.csv", parse_dates=["timestamp"])
        .set_index("timestamp")
        .sort_index()["close"]
    )
    vix = stress.zsr.daily(repo, "_INDIAVIX.csv")
    sessions = sorted(set(idx.index.normalize()))
    entry_offset = pd.Timedelta(hours=10, minutes=15)
    exit_offset = pd.Timedelta(hours=15)
    output = {name: [] for name in VARIANTS}
    for expiry in expiries:
        data = stress.load_expiry(repo, expiry.strftime("%Y-%m-%d"))
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
            # The stress loop's plan_entry refuses a missing spot or price before anything else;
            # here that refusal is the whole entry check, so it runs before atm_strike (which
            # cannot digest a NaN spot) and replaces the VIX and credit filters.
            spot = float(idx.loc[t0])
            if pd.isna(spot):
                continue
            sold_strike = rule.atm_strike(spot)
            sold, long_ = data.get(("CE", sold_strike)), data.get(("CE", sold_strike + rule.WIDTH))
            if sold is None or long_ is None or t0 not in sold.index or t0 not in long_.index:
                continue
            if pd.isna(float(sold.loc[t0, "close"])) or pd.isna(float(long_.loc[t0, "close"])):
                continue  # a price was missing: the only skip the ungated replay keeps
            end_ts = next_day + exit_offset
            for name in VARIANTS:
                trade = replay_trade_ungated(sold, long_, t0, end_ts, name, lot)
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


def summarize_or_zero(frame: pd.DataFrame) -> dict:
    """stress.summarize, but an empty day set reports zeros instead of raising on missing columns."""
    if frame.empty:
        return {
            "trades": 0,
            "realistic": 0,
            "doubled": 0,
            "mean": float("nan"),
            "t": float("nan"),
            "worst": 0,
            "dd": 0,
        }
    return stress.summarize(frame)


def _keys(frame: pd.DataFrame) -> set:
    return set(zip(frame["date"], frame["expiry"], strict=False)) if not frame.empty else set()


def main() -> int:
    gated_frames = stress.run(DATA_REPO)
    base = stress.summarize(gated_frames["base"])
    if (base["trades"], base["realistic"], base["doubled"]) != stress.BASE_EXPECTED:
        print(f"BASE MISMATCH: {base}; expected trades/net/net2x={stress.BASE_EXPECTED}")
        return 1
    ungated_frames = run_ungated(DATA_REPO)
    for name in VARIANTS:
        gated_frame, ungated_frame = gated_frames[name], ungated_frames[name]
        if gated_frame.empty or ungated_frame.empty:
            print(f"EMPTY FRAME ({name}): the replay produced no trades")
            return 1
        gated_keys = _keys(gated_frame)
        ungated_keys = _keys(ungated_frame)
        if gated_keys - ungated_keys:
            print(
                f"SUBSET MISMATCH ({name}): gated trades absent from the ungated replay: "
                f"{sorted(gated_keys - ungated_keys)}"
            )
            return 1
        shared = ungated_frame[
            [
                (day, expiry) in gated_keys
                for day, expiry in zip(ungated_frame["date"], ungated_frame["expiry"], strict=False)
            ]
        ]
        check, reference = stress.summarize(shared), stress.summarize(gated_frame)
        if (check["trades"], check["realistic"], check["doubled"]) != (
            reference["trades"],
            reference["realistic"],
            reference["doubled"],
        ):
            print(f"SUBSET MISMATCH ({name}): the shared trades do not reproduce the gated replay")
            return 1
        skipped = ungated_frame[
            [
                (day, expiry) not in gated_keys
                for day, expiry in zip(ungated_frame["date"], ungated_frame["expiry"], strict=False)
            ]
        ]
        for label, frame in (("gated", gated_frame), ("ungated", ungated_frame)):
            result = stress.summarize(frame)
            print(
                f"{name} {label}: trades={result['trades']} net_realistic={result['realistic']} "
                f"net_doubled={result['doubled']} mean={result['mean']:.2f} t={result['t']:.3f} "
                f"worst={result['worst']} deepest_fall={result['dd']}"
            )
        skipped_result = summarize_or_zero(skipped)
        print(
            f"{name} gate_skipped: trades={skipped_result['trades']} "
            f"net={skipped_result['realistic']} mean={skipped_result['mean']:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
