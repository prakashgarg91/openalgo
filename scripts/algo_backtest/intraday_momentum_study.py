"""Run the registered Nifty intraday momentum test (docs/algos/intraday-momentum-registration.md).

Needs the Nifty 1-minute file from fetch_index_1m.py. Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/intraday_momentum_study.py <data_repo> [out_dir]
"""

import json
import sys
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import linkage as lk  # noqa: E402

PREDICTORS = ("first30", "prev30", "gap")
CONDITIONS = ("all", "volatile", "calm", "expiry")


def _at(d: pd.DataFrame, day: pd.Timestamp, h: int, m: int, col: str) -> float:
    return float(d.loc[d.index == day + pd.Timedelta(hours=h, minutes=m), col].iloc[0])


def session_returns(minutes: pd.DataFrame) -> pd.DataFrame:
    """One row per complete session: first30, prev30, last30 and the opening gap (log returns)."""
    rows = []
    prev_close = None
    for day, d in minutes.groupby(minutes.index.normalize()):
        t = d.index.time
        if t[0] != dtime(9, 15) or t[-1] < dtime(15, 29):
            prev_close = None  # an incomplete session cannot give the next gap
            continue

        try:
            first30 = np.log(_at(d, day, 9, 44, "close") / _at(d, day, 9, 15, "open"))
            prev30 = np.log(_at(d, day, 14, 59, "close") / _at(d, day, 14, 30, "open"))
            last30 = np.log(_at(d, day, 15, 29, "close") / _at(d, day, 15, 0, "open"))
        except IndexError:
            prev_close = None
            continue
        gap = np.log(d["open"].iloc[0] / prev_close) if prev_close else np.nan
        rows.append(
            {"day": day, "first30": first30, "prev30": prev30, "last30": last30, "gap": gap}
        )
        prev_close = float(d["close"].iloc[-1])
    return pd.DataFrame(rows).set_index("day")


def expiry_flag(days: pd.DatetimeIndex) -> np.ndarray:
    """Weekly expiry: Thursday before 1 Sept 2025, Tuesday from then. Holiday shifts are not modelled."""
    weekday = np.where(days < pd.Timestamp("2025-09-01"), 3, 1)
    return days.dayofweek.to_numpy() == weekday


def run(sessions: pd.DataFrame, vix_prev: pd.Series) -> dict:
    df = sessions.join(vix_prev.rename("vix_prev"), how="left").dropna(subset=["last30"])
    half = len(df) // 2
    median = float(df["vix_prev"].iloc[:half].median())
    masks = {
        "all": np.ones(len(df), dtype=bool),
        "volatile": (df["vix_prev"] > median).to_numpy(),
        "calm": (df["vix_prev"] <= median).to_numpy(),
        "expiry": expiry_flag(df.index),
    }
    rows = []
    for cond in CONDITIONS:
        m = masks[cond]
        first, second = m.copy(), m.copy()
        first[half:] = False
        second[:half] = False
        for pred in PREDICTORS:
            x, y = df[pred].to_numpy(), df["last30"].to_numpy()
            b1, t1, n1 = lk.ols_hac(x[first], y[first])
            b2, t2, n2 = lk.ols_hac(x[second], y[second])
            rows.append(
                {
                    "condition": cond, "predictor": pred, "n_first": n1, "n_second": n2,
                    "beta_first": b1, "t_first": t1, "beta_second": b2, "t_second": t2,
                    "verified": bool(
                        not np.isnan(t2) and np.sign(b1) == np.sign(b2) and abs(t2) >= 2.0
                    ),
                }
            )  # fmt: skip
    x_all = df[list(PREDICTORS)].to_numpy()
    ok = ~np.isnan(x_all).any(axis=1)
    y = df["last30"].to_numpy()
    tr, te = ok.copy(), ok.copy()
    tr[half:] = False
    te[:half] = False
    coef = lk.ridge_fit(x_all[tr], y[tr], 1e-9)
    r2 = lk.r_squared_out(y[te], lk.ridge_predict(x_all[te], coef), float(np.mean(y[tr])))
    return {"sessions": len(df), "pairs": rows, "joint_r2_second_half": r2}


def main() -> int:
    repo = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else repo / "research" / "intraday_momentum"
    out_dir.mkdir(parents=True, exist_ok=True)
    minutes = pd.read_csv(repo / "index" / "nifty_1m.csv", parse_dates=["timestamp"]).set_index(
        "timestamp"
    )
    sessions = session_returns(minutes.sort_index())
    vix = pd.read_csv(repo / "context" / "daily" / "_INDIAVIX.csv", index_col=0)
    vix.index = pd.to_datetime(vix.index, utc=True)
    vix.index = pd.DatetimeIndex(vix.index.tz_convert("Asia/Kolkata").tz_localize(None)).normalize()
    vix_prev = vix["close"].shift(1).reindex(sessions.index)
    result = run(sessions, vix_prev)
    (out_dir / "summary.json").write_text(
        json.dumps(result, indent=2, default=float), encoding="utf-8"
    )
    print(
        f"{result['sessions']} sessions; joint model R2 second half {result['joint_r2_second_half']:.3f}"
    )
    print(pd.DataFrame(result["pairs"]).to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
