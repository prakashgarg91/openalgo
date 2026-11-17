"""Reproduce the gated ATM 200-wide call credit spread replay through services.algos.atm200_rule.

Read only: loads the data repo, prints a summary, writes no file and places no order. Every entry
and exit decision goes through the rule module. Data loading, the strike-free session rules and
the cost model are the replay's own helpers (imported, not re-written); its main() is not called.
Run: uv run python -I scripts/algo_backtest/atm200_replay_check.py
"""

import csv
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ written by the imports below

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # the worktree's services package must win the import

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from services.algos import atm200_rule as rule  # noqa: E402
from services.algos import eod_screen as es  # noqa: E402
from services.algos import nse_lots  # noqa: E402

DATA_REPO = Path("D:/Github/openalgo-data")
REPLAY_FILE = Path("D:/Github/openalgo-cloud/scripts/algo_backtest/zen_structure_replay.py")

_spec = importlib.util.spec_from_file_location("zen_structure_replay", REPLAY_FILE)
zsr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(zsr)  # defines load_expiry, daily, stats; does not run main()

REFERENCE = {
    "trades": 388,
    "net": 167102,
    "net2x": 105861,
    "mean": 431,
    "sd": 3552,
    "t": 2.39,
    "worst": -8935,
    "dd": 43723,
}


def _hm(text: str) -> pd.Timedelta:
    h, m = (int(p) for p in text.split(":"))
    return pd.Timedelta(hours=h, minutes=m)


def run(repo: Path) -> pd.DataFrame:
    with (repo / "MANIFEST.csv").open(encoding="utf-8") as fh:
        expiries = sorted(pd.Timestamp(r["expiry"]) for r in csv.DictReader(fh))
    idx = (
        pd.read_csv(repo / "index" / "nifty_1m.csv", parse_dates=["timestamp"])
        .set_index("timestamp")
        .sort_index()["close"]
    )
    vix = zsr.daily(repo, "_INDIAVIX.csv")
    sessions = sorted(set(idx.index.normalize()))
    entry_offset = _hm(rule.ENTRY_TIME)
    exit_offset = _hm(rule.LAST_EXIT_TIME)
    rows = []
    for e in expiries:
        data = zsr.load_expiry(repo, e.strftime("%Y-%m-%d"))
        lot = nse_lots.nifty_lot(e)
        if lot is None:
            continue
        for d in sessions:
            if not (0 < (e - d).days <= rule.MAX_DAYS_TO_EXPIRY):
                continue
            nxt = [s for s in sessions if s > d]
            if not nxt:
                continue
            d1 = nxt[0]
            if d1 > e:
                continue
            t0 = d + entry_offset
            if t0 not in idx.index:
                continue
            spot = idx.get(t0)
            prev = [s for s in sessions if s < d]
            vix_prev = vix.get(prev[-1]) if prev else None
            sold_k = rule.atm_strike(float(spot))
            bought_k = sold_k + rule.WIDTH
            sold, long_ = data.get(("CE", sold_k)), data.get(("CE", bought_k))
            if sold is None or long_ is None or t0 not in sold.index or t0 not in long_.index:
                continue
            so, lo = float(sold.loc[t0]), float(long_.loc[t0])
            plan = rule.plan_entry(float(spot), vix_prev, so, lo)
            if (
                plan.skipped_reason is not None
                or plan.sold_strike != sold_k
                or plan.bought_strike != bought_k
            ):
                continue
            credit = plan.credit_points

            spread = (sold - long_).dropna()
            path = spread.loc[t0 : d1 + exit_offset].iloc[1:]
            if path.empty:
                continue
            n = len(path)
            exit_v, why, exit_ts = float(path.iloc[-1]), "time", path.index[-1]
            for i, (ts, v) in enumerate(path.items()):
                reason = rule.exit_decision(credit, float(v), is_last_bar=(i == n - 1))
                if reason is not None:
                    exit_v, why, exit_ts = float(v), reason, ts
                    break
            sx = float(sold.reindex(path.index).ffill().loc[exit_ts])
            lx = float(long_.reindex(path.index).ffill().loc[exit_ts])
            cost = es.leg_cost(-1, so, sx, d, d1, lot) + es.leg_cost(1, lo, lx, d, d1, lot)
            gross = rule.pnl_rupees(credit, exit_v, lot)
            rows.append(
                {
                    "date": d,
                    "side": "CE",
                    "expiry": e,
                    "credit": credit,
                    "exit": exit_v,
                    "why": why,
                    "gross": gross,
                    "cost": cost,
                    "net": gross - cost,
                    "net2x": gross - 2 * cost,
                    "vix_prev": vix_prev,
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    df = run(DATA_REPO)
    if df.empty:
        print("no trades")
        return 1
    ordered = df.sort_values("date")
    net = df["net"]
    n = len(df)
    mean = float(net.mean())
    sd = float(net.std(ddof=1))
    t = mean / (sd / np.sqrt(n))
    months = df.groupby(pd.to_datetime(df["date"]).dt.to_period("M"))["net"].sum()
    neg_months = int((months < 0).sum())
    dd = zsr.stats(ordered)["dd"]
    got = {
        "trades": n,
        "net": round(float(net.sum())),
        "net2x": round(float(df["net2x"].sum())),
        "mean": round(mean),
        "sd": round(sd),
        "t": round(t, 2),
        "worst": round(float(net.min())),
        "dd": dd,
    }
    print(f"trades: {n}")
    print(f"net realistic: {got['net']}")
    print(f"net doubled: {got['net2x']}")
    print(f"mean: {got['mean']}  sd: {got['sd']}  t: {got['t']}")
    print(f"negative months: {neg_months} of {len(months)}")
    print(f"worst trade: {got['worst']}")
    print(f"deepest fall: {got['dd']}")
    print(
        f"exits: target {int((df.why == 'target').sum())}, stop {int((df.why == 'stop').sum())}, time {int((df.why == 'time').sum())}"
    )
    verdicts = []
    for key, ref in REFERENCE.items():
        ok = abs(got[key] - ref) <= 0.01 * abs(ref)
        verdicts.append(ok)
        print(f"  {key}: got {got[key]} ref {ref} {'match' if ok else 'MISMATCH'}")
    print("RESULT: MATCH within 1 percent on every figure" if all(verdicts) else "RESULT: MISMATCH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
