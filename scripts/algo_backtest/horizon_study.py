"""Run the registered multi-horizon linkage study (docs/algos/horizon-study-registration.md).

Inputs known at the Indian close of day t, outcomes over the next 5 and 20 trading days.
Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/horizon_study.py <data_repo> [out_dir]
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.algo_backtest import fetch_context_data as ctxmod  # noqa: E402
from scripts.algo_backtest import linkage_study as ls  # noqa: E402
from services.algos import linkage as lk  # noqa: E402

WINDOWS = (1, 5, 20, 60)
OUTCOMES = ("ret5", "ret20", "lvol5", "lvol20", "dd5")
LAGS = {"ret5": 10, "lvol5": 10, "dd5": 10, "ret20": 40, "lvol20": 40}
INDIAN = {ctxmod.safe(s) for g in ("india_indices", "india_heavyweights") for s in ctxmod.GROUPS[g]}
ASIA = {ctxmod.safe(s) for s in ctxmod.GROUPS["asia"]}
BLOCK = 60
DRAWS = 300
MIN_OBS = 500
GAIN_MIN = 0.02


def hours_for(stem: str) -> float:
    if stem in INDIAN:
        return 6.25
    if stem in ASIA:
        return 8.0
    if stem in ls.FX:
        return 24.0
    if stem in ls.FUTURES:
        return 23.0
    return 9.0


def outcomes(close: pd.Series) -> pd.DataFrame:
    c = np.log(close.astype(float))
    r = c.diff()
    out = pd.DataFrame(index=close.index)
    for h in (5, 20):
        out[f"ret{h}"] = c.shift(-h) - c
        fwd = (r**2).rolling(h).sum().shift(-h)
        out[f"lvol{h}"] = np.log(np.sqrt(252 / h * fwd))
    out["dd5"] = pd.concat([c.shift(-k) - c for k in range(1, 6)], axis=1).min(axis=1, skipna=False)
    return out.replace([np.inf, -np.inf], np.nan)


def build_inputs(ctx: Path, nifty: pd.DataFrame, cuts: pd.DatetimeIndex) -> pd.DataFrame:
    cols: dict[str, np.ndarray] = {}
    levels: dict[str, pd.Series] = {}
    for path in sorted(ctx.glob("*.csv")):
        stem = path.stem
        if stem == "_INDIAVIX":
            continue
        bars = ls.load(path)
        close = bars["close"].astype(float)
        close = close[close > 0] if stem not in ls.YIELDS else close
        if len(close) < 300:
            continue
        base = close if stem in ls.YIELDS else np.log(close)
        levels[stem] = close
        for w in WINDOWS:
            cols[f"{stem}__r{w}"] = lk.known_before(
                base.diff(w), close.index, hours_for(stem), cuts
            ).to_numpy()
    vix_in = ls.load(ctx / "_INDIAVIX.csv")["close"].astype(float)
    ln_india = lk.known_before(np.log(vix_in), vix_in.index, 6.25, cuts)
    cols["derived__ln_india_vix"] = ln_india.to_numpy()
    if "_VIX" in levels:
        us = lk.known_before(np.log(levels["_VIX"]), levels["_VIX"].index, 9.0, cuts)
        cols["derived__us_over_india_vix"] = (us - ln_india).to_numpy()
    if "_TNX" in levels and "_IRX" in levels:
        t10 = lk.known_before(levels["_TNX"], levels["_TNX"].index, 9.0, cuts)
        t3m = lk.known_before(levels["_IRX"], levels["_IRX"].index, 9.0, cuts)
        cols["derived__curve_10y_3m"] = (t10 - t3m).to_numpy()
    r = np.log(nifty["close"].astype(float)).diff()
    own = np.sqrt(252 * (r**2).rolling(20).mean())
    cols["derived__own_rv20"] = own.reindex(nifty.index).to_numpy()
    return pd.DataFrame(cols, index=nifty.index)


def pair_table(x: pd.DataFrame, y: pd.DataFrame, half: int) -> pd.DataFrame:
    rows = []
    for name in x.columns:
        xv = x[name].to_numpy()
        sd = np.nanstd(xv[:half])
        if not sd:
            continue
        xv = (xv - np.nanmean(xv[:half])) / sd
        for out in OUTCOMES:
            yv = y[out].to_numpy()
            n_d = int((~(np.isnan(xv[:half]) | np.isnan(yv[:half]))).sum())
            n_v = int((~(np.isnan(xv[half:]) | np.isnan(yv[half:]))).sum())
            if n_d < MIN_OBS or n_v < MIN_OBS:
                continue
            b, t, _ = lk.ols_hac(xv[:half], yv[:half], LAGS[out])
            rows.append({"input": name, "outcome": out, "beta_disc": b, "t_disc": t,
                         "p_disc": lk.two_sided_p(t)})  # fmt: skip
    table = pd.DataFrame(rows)
    table["selected"] = lk.benjamini_hochberg(table["p_disc"].to_numpy(), ls.Q)
    return table


def verify(table: pd.DataFrame, x: pd.DataFrame, y: pd.DataFrame, half: int) -> pd.DataFrame:
    out = table.copy()
    bs, ts = [], []
    for _, r in out.iterrows():
        if not r["selected"]:
            bs.append(np.nan)
            ts.append(np.nan)
            continue
        xv = x[r["input"]].to_numpy()
        xv = (xv - np.nanmean(xv[:half])) / np.nanstd(xv[:half])
        b, t, _ = lk.ols_hac(xv[half:], y[r["outcome"]].to_numpy()[half:], LAGS[r["outcome"]])
        bs.append(b)
        ts.append(t)
    out["beta_ver"], out["t_ver"] = bs, ts
    out["verified"] = (
        out["selected"]
        & (np.sign(out["beta_disc"]) == np.sign(out["beta_ver"]))
        & (out["t_ver"].abs() >= ls.VERIFY_T)
    )
    return out


def chance(sel: pd.DataFrame, x: pd.DataFrame, y: pd.DataFrame, half: int) -> dict:
    rng = np.random.default_rng(ls.SEED)
    std = {}
    for name in sel["input"].unique():
        xv = x[name].to_numpy()
        std[name] = ((xv - np.nanmean(xv[:half])) / np.nanstd(xv[:half]))[half:]
    pairs = list(zip(sel["input"], sel["outcome"], np.sign(sel["beta_disc"]), strict=True))
    shares = []
    for _ in range(DRAWS):
        shuf = {o: lk.block_shuffle(y[o].to_numpy()[half:], rng, BLOCK) for o in OUTCOMES}
        hit = 0
        for name, out, sign in pairs:
            b, t, _ = lk.ols_hac(std[name], shuf[out], LAGS[out])
            if not np.isnan(t) and np.sign(b) == sign and abs(t) >= ls.VERIFY_T:
                hit += 1
        shares.append(hit / max(len(pairs), 1))
    return {"mean": float(np.mean(shares)), "p95": float(np.quantile(shares, 0.95))}


def joint(x: pd.DataFrame, y: pd.DataFrame, half: int) -> list[dict]:
    m = x.to_numpy()
    mu, sd = np.nanmean(m[:half], axis=0), np.nanstd(m[:half], axis=0)
    sd[~np.isfinite(sd) | (sd == 0)] = 1.0
    z = np.nan_to_num((m - mu) / sd)
    base_names = ["derived__ln_india_vix", "derived__own_rv20"]
    base_names.append("_NSEI__r20")
    base_cols = [list(x.columns).index(c) for c in base_names if c in x.columns]
    res = []
    for out in OUTCOMES:
        yv = y[out].to_numpy()
        ok = ~np.isnan(yv)
        tr, te = ok.copy(), ok.copy()
        tr[half:] = False
        te[:half] = False
        alpha = lk.choose_alpha(z[tr], yv[tr])
        full = lk.ridge_predict(z[te], lk.ridge_fit(z[tr], yv[tr], alpha))
        base = lk.ridge_predict(
            z[te][:, base_cols], lk.ridge_fit(z[tr][:, base_cols], yv[tr], 1e-6)
        )
        mean = float(np.mean(yv[tr]))
        r_full = lk.r_squared_out(yv[te], full, mean)
        r_base = lk.r_squared_out(yv[te], base, mean)
        res.append({"outcome": out, "alpha": alpha, "r2_full": r_full, "r2_baseline": r_base,
                    "gain": r_full - r_base, "counts": bool(r_full - r_base >= GAIN_MIN)})  # fmt: skip
    return res


def main() -> int:
    repo = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else repo / "research" / "horizon"
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = repo / "context" / "daily"
    nifty = ls.load(ctx / "_NSEI.csv")
    nifty = nifty[(nifty[["open", "close"]] > 0).all(axis=1)]
    nifty = nifty[nifty.index > ls.load(ctx / "_INDIAVIX.csv").index[0]]
    cuts = pd.DatetimeIndex(nifty.index.normalize() + pd.Timedelta(hours=10))
    x = build_inputs(ctx, nifty, cuts)
    y = outcomes(nifty["close"])
    y.index = x.index
    half = len(nifty) // 2
    print(f"{len(nifty)} days; {x.shape[1]} inputs; split {nifty.index[half]:%Y-%m-%d}")
    table = pair_table(x, y, half)
    table.to_csv(out_dir / "discovery.csv", index=False, float_format="%.6g")
    print(f"Pairs tried {len(table)}; selected {int(table['selected'].sum())}. Verification now.")
    res = verify(table, x, y, half)
    res.to_csv(out_dir / "verification.csv", index=False, float_format="%.6g")
    sel = res[res["selected"]]
    summary = {
        "days": len(nifty), "inputs": x.shape[1], "pairs_tried": len(res),
        "selected": int(len(sel)), "verified": int(sel["verified"].sum()),
        "by_outcome": {
            o: {"selected": int(sel[sel["outcome"] == o].shape[0]),
                "verified": int(sel[(sel["outcome"] == o) & sel["verified"]].shape[0])}
            for o in OUTCOMES
        },
        "chance": chance(sel, x, y, half),
        "joint_model": joint(x, y, half),
    }  # fmt: skip
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    top = (
        sel[sel["verified"]].assign(a=lambda d: d["t_ver"].abs()).sort_values("a", ascending=False)
    )
    print(
        top[["input", "outcome", "beta_disc", "t_disc", "beta_ver", "t_ver"]]
        .head(25)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
