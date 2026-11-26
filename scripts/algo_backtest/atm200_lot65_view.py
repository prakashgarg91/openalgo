"""The six timing variants of the frozen ATM 200 replay at one constant lot of 65 (read only).

atm200_timing_stress sizes every trade with its expiry's real lot from nse_lots.nifty_lot (25, 75
or 65 across our data), so the eras are not comparable in rupees. This view answers one question:
what each variant looks like when the lot is 65 on every expiry. The variants, the trade selection
and the cost model are that script's; only the lot differs, so its run loop is copied here with the
nse_lots lookup replaced by the constant (a constant lot is never None, so the original's None skip
cannot fire). Each line prints trades, net realistic, net doubled, mean, t, worst trade and deepest
fall, with the deepest fall from zen_structure_replay.stats on trades in date order.

Read only: loads the data repo, writes no file, places no order. Run from the repo root:
  D:/Github/openalgo-cloud/.venv/Scripts/python.exe -m scripts.algo_backtest.atm200_lot65_view
"""

import csv
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ written by the imports below

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # the worktree's services package must win the import

import pandas as pd  # noqa: E402

from scripts.algo_backtest.atm200_timing_stress import (  # noqa: E402
    VARIANTS,
    load_expiry,
    replay_trade,
    summarize,
    zsr,
)
from services.algos import atm200_rule as rule  # noqa: E402
from services.algos import eod_screen as es  # noqa: E402

LOT = 65  # the one lot for every trade and every cost, whatever the expiry's own lot was
DATA_REPO = Path("D:/Github/openalgo-data")


def run(repo: Path) -> dict[str, pd.DataFrame]:
    """atm200_timing_stress.run with the lot fixed at 65: same loop, constant lot."""
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
                trade = replay_trade(sold, long_, t0, end_ts, float(plan.credit_points), name, LOT)
                if trade is None:
                    continue
                cost = es.leg_cost(-1, trade["sold_entry"], trade["sold_exit"], day, next_day, LOT)
                cost += es.leg_cost(1, trade["long_entry"], trade["long_exit"], day, next_day, LOT)
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


def main() -> int:
    frames = run(DATA_REPO)
    for name, frame in frames.items():
        result = summarize(frame)
        print(
            f"{name}: trades={result['trades']} net_realistic={result['realistic']} "
            f"net_doubled={result['doubled']} mean={result['mean']:.2f} t={result['t']:.3f} "
            f"worst={result['worst']} deepest_fall={result['dd']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
