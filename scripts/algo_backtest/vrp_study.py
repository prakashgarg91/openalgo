"""Run the registered variance risk premium test (docs/algos/vrp-registration.md).

India VIX against the Nifty volatility that follows over five trading days, and whether the
expected premium predicts how well selling premium would have done. Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/vrp_study.py <data_repo> [out_dir]
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import linkage as lk  # noqa: E402

H = 5
NW = 10
CRASH = (pd.Timestamp("2020-02-01"), pd.Timestamp("2020-04-30"))


def load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index, utc=True)
    out = frame.sort_index()
    out.index = pd.DatetimeIndex(out.index.tz_convert("Asia/Kolkata").tz_localize(None)).normalize()
    return out[~out.index.duplicated(keep="last")]


def mean_nw(y: np.ndarray, lags: int = NW) -> tuple[float, float]:
    """Mean and its Newey-West t-statistic."""
    y = y[~np.isnan(y)]
    n = len(y)
    if n < 30:
        return float("nan"), float("nan")
    e = y - y.mean()
    s = float(e @ e)
    for lag in range(1, lags + 1):
        s += 2 * (1 - lag / (lags + 1.0)) * float(e[lag:] @ e[:-lag])
    se = float(np.sqrt(s)) / n
    return float(y.mean()), float(y.mean() / se) if se else float("nan")


def build(ctx: Path) -> pd.DataFrame:
    nifty = load(ctx / "_NSEI.csv")
    vix = load(ctx / "_INDIAVIX.csv")
    close = nifty["close"][nifty["close"] > 0]
    r = np.log(close).diff()
    df = pd.DataFrame({"iv": (vix["close"] / 100).reindex(close.index)}, index=close.index)
    df["rv1"] = np.sqrt(252) * r.abs()
    df["rv5"] = np.sqrt(252 * (r**2).rolling(5).mean())
    df["rv20"] = np.sqrt(252 * (r**2).rolling(20).mean())
    fwd = (r**2).rolling(H).sum().shift(-H)
    df["rv_fwd"] = np.sqrt(252 / H * fwd)
    df = df.dropna()
    df = df[df["iv"] > 0]
    df = df[df.index > vix.index[0]]
    df["premium"] = df["iv"] - df["rv_fwd"]
    df["payoff"] = df["iv"] ** 2 - df["rv_fwd"] ** 2
    return df


def describe(y: np.ndarray, p: np.ndarray) -> dict:
    m, t = mean_nw(y)
    return {
        "days": int(len(y)),
        "mean_payoff": m,
        "t": t,
        "share_positive": float(np.mean(p > 0)),
        "mean_premium": float(np.mean(p)),
        "worst_1pct_payoff": float(np.quantile(y, 0.01)),
    }


def main() -> int:
    repo = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else repo / "research" / "vrp"
    out_dir.mkdir(parents=True, exist_ok=True)
    df = build(repo / "context" / "daily")
    half = len(df) // 2
    first, second = df.iloc[:half], df.iloc[half:]
    print(
        f"{len(df)} days; first half to {first.index[-1]:%Y-%m-%d}, second from {second.index[0]:%Y-%m-%d}"
    )
    summary: dict = {"days": len(df)}
    for name, part in (("first_half", first), ("second_half", second), ("all", df)):
        summary[name] = describe(part["payoff"].to_numpy(), part["premium"].to_numpy())
    crash = (df.index >= CRASH[0]) & (df.index <= CRASH[1])
    nc = df[~crash]
    summary["all_without_crash_window"] = describe(
        nc["payoff"].to_numpy(), nc["premium"].to_numpy()
    )
    summary["second_half_without_crash_window"] = describe(
        second[~((second.index >= CRASH[0]) & (second.index <= CRASH[1]))]["payoff"].to_numpy(),
        second[~((second.index >= CRASH[0]) & (second.index <= CRASH[1]))]["premium"].to_numpy(),
    )
    # HAR forecast of the forward realised volatility, fitted on the first half only
    x = df[["rv1", "rv5", "rv20"]].to_numpy()
    coef = lk.ridge_fit(x[:half], df["rv_fwd"].to_numpy()[:half], 1e-9)
    df["har"] = lk.ridge_predict(x, coef)
    df["expected_premium"] = df["iv"] - df["har"]
    cuts = np.quantile(df["expected_premium"].to_numpy()[:half], [0.2, 0.4, 0.6, 0.8])
    df["q"] = np.searchsorted(cuts, df["expected_premium"].to_numpy()) + 1
    second = df.iloc[half:]
    rows = []
    for q in range(1, 6):
        s = second[second["q"] == q]
        if len(s) == 0:
            continue
        rows.append({"quintile": q, **describe(s["payoff"].to_numpy(), s["premium"].to_numpy())})
    summary["second_half_by_expected_premium"] = rows
    top, bottom = second[second["q"] == 5], second[second["q"] == 1]
    diff = (
        float(top["payoff"].mean() - bottom["payoff"].mean())
        if len(top) and len(bottom)
        else float("nan")
    )
    # Newey-West t for the difference using a dummy regression across the two groups
    both = pd.concat([top.assign(d=1.0), bottom.assign(d=0.0)]).sort_index()
    _, t_diff, _ = lk.ols_hac(both["d"].to_numpy(), both["payoff"].to_numpy(), NW)
    summary["quintile5_minus_1"] = {"payoff": diff, "t": t_diff}
    summary["har_r2_second_half"] = lk.r_squared_out(
        second["rv_fwd"].to_numpy(),
        second["har"].to_numpy(),
        float(first["rv_fwd"].mean()),
    )
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for k in (
        "first_half",
        "second_half",
        "all",
        "all_without_crash_window",
        "second_half_without_crash_window",
    ):
        v = summary[k]
        print(
            f"{k}: days {v['days']}, mean premium {v['mean_premium'] * 100:.2f} vol pts, mean payoff "
            f"{v['mean_payoff'] * 1e4:.1f} (t {v['t']:.1f}), positive {v['share_positive']:.0%}, worst 1% {v['worst_1pct_payoff'] * 1e4:.0f}"
        )
    print("second half by expected-premium quintile (payoff in variance points x 1e4):")
    for r in rows:
        print(
            f"  q{r['quintile']}: days {r['days']}, premium {r['mean_premium'] * 100:.2f}, payoff {r['mean_payoff'] * 1e4:.1f} (t {r['t']:.1f}), positive {r['share_positive']:.0%}, worst 1% {r['worst_1pct_payoff'] * 1e4:.0f}"
        )
    print(
        f"quintile 5 minus 1: payoff {diff * 1e4:.1f}, t {t_diff:.2f}; HAR R2 second half {summary['har_r2_second_half']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
