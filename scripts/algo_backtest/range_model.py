"""Run the registered range model (docs/algos/range-model-registration.md).

Fits six models for the Nifty's daily range on the first half of the days and scores them once on
the second half. Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/range_model.py <data_repo> [out_dir]
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import linkage as lk  # noqa: E402

MODELS = {
    "1_baseline": ["vix_prev", "range_1"],
    "2_plus_vix_open": ["vix_prev", "range_1", "vix_open"],
    "3_plus_range_avgs": ["vix_prev", "range_1", "range_5", "range_20"],
    "4_plus_abs_gap": ["vix_prev", "range_1", "abs_gap"],
    "5_plus_us_vix": ["vix_prev", "range_1", "us_vix"],
    "6_full": [
        "vix_prev",
        "range_1",
        "vix_open",
        "range_5",
        "range_20",
        "abs_gap",
        "us_vix",
        "wd_1",
        "wd_2",
        "wd_3",
        "wd_4",
    ],  # fmt: skip
}


def load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index, utc=True)
    return frame.sort_index()


def build(ctx: Path) -> pd.DataFrame:
    nifty = load(ctx / "_NSEI.csv")
    nifty = nifty[(nifty[["open", "high", "low", "close"]] > 0).all(axis=1)]
    vix = load(ctx / "_INDIAVIX.csv")
    vix = vix[(vix[["open", "close"]] > 0).all(axis=1)]
    usv = load(ctx / "_VIX.csv")
    opens = nifty.index
    rng = (nifty["high"] - nifty["low"]) / nifty["open"]
    df = pd.DataFrame(index=opens)
    df["target"] = np.log(rng)
    prev_close = nifty["close"].shift(1)
    df["abs_gap"] = np.abs(np.log(nifty["open"] / prev_close))
    df["range_1"] = rng.shift(1)
    df["range_5"] = rng.shift(1).rolling(5).mean()
    df["range_20"] = rng.shift(1).rolling(20).mean()
    df["vix_prev"] = lk.known_before(np.log(vix["close"]), vix.index, 9, opens).to_numpy()
    df["vix_open"] = np.log(vix["open"]).reindex(opens)
    df["us_vix"] = lk.known_before(
        np.log(usv["close"].astype(float)), usv.index, 9, opens
    ).to_numpy()
    for d in (1, 2, 3, 4):
        df[f"wd_{d}"] = (opens.tz_convert("Asia/Kolkata").dayofweek == d).astype(float)
    df = df[df.index > vix.index[0]]
    return df.replace([np.inf, -np.inf], np.nan).dropna()


def main() -> int:
    repo = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else repo / "research" / "range_model"
    out_dir.mkdir(parents=True, exist_ok=True)
    df = build(repo / "context" / "daily")
    half = len(df) // 2
    print(
        f"{len(df)} days; fit {df.index[0]:%Y-%m-%d} to {df.index[half - 1]:%Y-%m-%d};"
        f" score {df.index[half]:%Y-%m-%d} to {df.index[-1]:%Y-%m-%d}"
    )
    y = df["target"].to_numpy()
    yd, yv = y[:half], y[half:]
    mean = float(np.mean(yd))
    results, preds = [], {}
    for name, cols in MODELS.items():
        x = df[cols].to_numpy()
        coef = lk.ridge_fit(x[:half], yd, 1e-9)
        pred = lk.ridge_predict(x[half:], coef)
        preds[name] = (lk.ridge_predict(x[:half], coef), pred)
        results.append(
            {
                "model": name,
                "r2_out": lk.r_squared_out(yv, pred, mean),
                "rank_corr": float(spearmanr(pred, yv).statistic),
            }
        )
    table = pd.DataFrame(results)
    print(table.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    fit_pred, val_pred = preds["6_full"]
    cuts = np.quantile(fit_pred, [0.2, 0.4, 0.6, 0.8])
    group = np.searchsorted(cuts, val_pred)
    realized = np.exp(yv)
    cal = [
        {"group": g + 1, "days": int((group == g).sum()), "mean_range_pct": float(realized[group == g].mean() * 100)}
        for g in range(5)
    ]  # fmt: skip
    print(pd.DataFrame(cal).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    ratio = cal[-1]["mean_range_pct"] / cal[0]["mean_range_pct"]
    base = table.set_index("model")
    verdict = bool(
        base.loc["6_full", "r2_out"] > base.loc["1_baseline", "r2_out"]
        and base.loc["6_full", "rank_corr"] > base.loc["1_baseline", "rank_corr"]
        and all(cal[i]["mean_range_pct"] < cal[i + 1]["mean_range_pct"] for i in range(4))
    )
    summary = {
        "days": len(df),
        "models": results,
        "calibration": cal,
        "top_to_bottom": ratio,
        "beats_baseline": verdict,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        f"top group over bottom group: {ratio:.2f}x; full model beats baseline on the registered test: {verdict}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
