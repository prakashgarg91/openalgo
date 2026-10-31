"""Run the registered cross-market linkage study (docs/algos/linkage-study-registration.md).

Reads the daily context series from the data repository, finds links in the first half of the
Nifty's days, writes that discovery list to a file, and only then looks at the second half.
Read only; places no order, uses no token.

Usage:
    uv run python scripts/algo_backtest/linkage_study.py <data_repo> [out_dir]
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import linkage as lk  # noqa: E402

TARGETS = ("gap", "intraday", "range", "close_to_close")
FX = {"AUDUSD_X", "EURUSD_X", "GBPUSD_X", "USDCNY_X", "USDINR_X", "USDJPY_X"}
FUTURES = {
    "BZ_F", "CL_F", "DX-Y.NYB", "ES_F", "GC_F", "HG_F", "NG_F", "NQ_F", "RTY_F", "SI_F", "YM_F",
}  # fmt: skip
YIELDS = {"_TNX", "_FVX", "_IRX"}
MIN_OBS = 500
Q = 0.05
VERIFY_T = 2.0
DRAWS = 1000
SEED = 20261031


def load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index, utc=True)
    return frame.sort_index()


def hours_for(stem: str) -> int:
    if stem in FX:
        return lk.NIFTY_OPEN_NEWEST_HOURS["fx"]
    if stem in FUTURES:
        return lk.NIFTY_OPEN_NEWEST_HOURS["futures"]
    return lk.NIFTY_OPEN_NEWEST_HOURS["other"]


def nifty_targets(nifty: pd.DataFrame) -> pd.DataFrame:
    n = nifty[(nifty["open"] > 0) & (nifty["close"] > 0) & (nifty["high"] > 0) & (nifty["low"] > 0)]
    prev = n["close"].shift(1)
    out = pd.DataFrame(
        {
            "gap": np.log(n["open"] / prev),
            "intraday": np.log(n["close"] / n["open"]),
            "range": (n["high"] - n["low"]) / n["open"],
            "close_to_close": np.log(n["close"] / prev),
        }
    )
    out = out.dropna()
    glitch = (out["gap"].abs() > 0.15) | (out["close_to_close"].abs() > 0.2)
    print(f"Nifty days {len(out)}, dropped {int(glitch.sum())} with an impossible move")
    return out[~glitch]


def build_features(ctx: Path, nifty: pd.DataFrame, opens: pd.DatetimeIndex) -> pd.DataFrame:
    cols = {}
    for path in sorted(ctx.glob("*.csv")):
        stem = path.stem
        bars = load(path)
        kind = "diff" if stem in YIELDS else "log"
        ret = lk.session_return(bars, kind)
        cols[stem] = lk.known_before(ret, bars.index, hours_for(stem), opens).to_numpy()
    vix = load(ctx / "_INDIAVIX.csv")
    cols["base_ln_indiavix"] = lk.known_before(
        np.log(vix["close"].astype(float)), vix.index, 9, opens
    ).to_numpy()
    own_range = (nifty["high"] - nifty["low"]) / nifty["open"]
    cols["base_own_range"] = lk.known_before(own_range, nifty.index, 9, opens).to_numpy()
    return pd.DataFrame(cols, index=opens)


def discover(feats: pd.DataFrame, targets: pd.DataFrame, half: int) -> pd.DataFrame:
    rows = []
    for name in feats.columns:
        x = feats[name].to_numpy()
        for target in TARGETS:
            y = targets[target].to_numpy()
            n_d = int((~(np.isnan(x[:half]) | np.isnan(y[:half]))).sum())
            n_v = int((~(np.isnan(x[half:]) | np.isnan(y[half:]))).sum())
            if n_d < MIN_OBS or n_v < MIN_OBS:
                continue
            beta, t, _ = lk.ols_hac(x[:half], y[:half])
            rows.append(
                {"feature": name, "target": target, "n_disc": n_d, "n_ver": n_v,
                 "beta_disc": beta, "t_disc": t, "p_disc": lk.two_sided_p(t)}
            )  # fmt: skip
    table = pd.DataFrame(rows)
    table["selected"] = lk.benjamini_hochberg(table["p_disc"].to_numpy(), Q)
    return table


def verify(
    table: pd.DataFrame, feats: pd.DataFrame, targets: pd.DataFrame, half: int
) -> pd.DataFrame:
    out = table.copy()
    betas, ts = [], []
    for _, row in out.iterrows():
        if not row["selected"]:
            betas.append(np.nan)
            ts.append(np.nan)
            continue
        beta, t, _ = lk.ols_hac(
            feats[row["feature"]].to_numpy()[half:], targets[row["target"]].to_numpy()[half:]
        )
        betas.append(beta)
        ts.append(t)
    out["beta_ver"], out["t_ver"] = betas, ts
    out["same_sign"] = np.sign(out["beta_disc"]) == np.sign(out["beta_ver"])
    out["verified"] = out["selected"] & out["same_sign"] & (out["t_ver"].abs() >= VERIFY_T)
    return out


def chance_share(sel: pd.DataFrame, feats: pd.DataFrame, targets: pd.DataFrame, half: int) -> dict:
    rng = np.random.default_rng(SEED)
    shares = []
    pairs = list(zip(sel["feature"], sel["target"], np.sign(sel["beta_disc"]), strict=True))
    for _ in range(DRAWS):
        shuffled = {t: lk.block_shuffle(targets[t].to_numpy()[half:], rng) for t in TARGETS}
        hit = 0
        for feat, target, sign in pairs:
            beta, t, _ = lk.ols_hac(feats[feat].to_numpy()[half:], shuffled[target])
            if not np.isnan(t) and np.sign(beta) == sign and abs(t) >= VERIFY_T:
                hit += 1
        shares.append(hit / max(len(pairs), 1))
    return {"mean": float(np.mean(shares)), "p95": float(np.quantile(shares, 0.95))}


def joint(feats: pd.DataFrame, targets: pd.DataFrame, half: int) -> list[dict]:
    x = feats.to_numpy()
    mu, sd = np.nanmean(x[:half], axis=0), np.nanstd(x[:half], axis=0)
    sd[sd == 0] = 1.0
    z = np.nan_to_num((x - mu) / sd)
    base_cols = [i for i, c in enumerate(feats.columns) if c.startswith("base_")]
    out = []
    for target in TARGETS:
        y = targets[target].to_numpy()
        yd, yv = y[:half], y[half:]
        alpha = lk.choose_alpha(z[:half], yd)
        full = lk.ridge_predict(z[half:], lk.ridge_fit(z[:half], yd, alpha))
        base = lk.ridge_predict(
            z[half:][:, base_cols], lk.ridge_fit(z[:half][:, base_cols], yd, 1e-6)
        )
        mean = float(np.mean(yd))
        out.append(
            {
                "target": target,
                "alpha": alpha,
                "r2_full": lk.r_squared_out(yv, full, mean),
                "r2_baseline": lk.r_squared_out(yv, base, mean),
                "rank_corr_full": float(spearmanr(full, yv).statistic),
                "rank_corr_baseline": float(spearmanr(base, yv).statistic),
            }
        )
    return out


def main() -> int:
    repo = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else repo / "research" / "linkage"
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = repo / "context" / "daily"
    nifty_raw = load(ctx / "_NSEI.csv")
    targets = nifty_targets(nifty_raw)
    vix_start = load(ctx / "_INDIAVIX.csv").index[0]
    targets = targets[targets.index > vix_start]
    opens = targets.index
    feats = build_features(ctx, nifty_raw, opens)
    half = len(targets) // 2
    print(f"{len(targets)} days; discovery {targets.index[0]:%Y-%m-%d} to {targets.index[half - 1]:%Y-%m-%d};"
          f" verification {targets.index[half]:%Y-%m-%d} to {targets.index[-1]:%Y-%m-%d}")  # fmt: skip
    table = discover(feats, targets, half)
    table.to_csv(out_dir / "discovery.csv", index=False, float_format="%.6g")
    sel = table[table["selected"]]
    print(f"Pairs tried: {len(table)}; selected in discovery (FDR {Q:.0%}): {len(sel)}")
    print("Discovery list written; the second half is looked at only now.")
    result = verify(table, feats, targets, half)
    result.to_csv(out_dir / "verification.csv", index=False, float_format="%.6g")
    chosen = result[result["selected"]]
    summary = {
        "days": len(targets),
        "pairs_tried": len(table),
        "selected": int(len(chosen)),
        "verified": int(chosen["verified"].sum()),
        "same_sign": int(chosen["same_sign"].sum()),
        "sign_flipped": int((~chosen["same_sign"]).sum()),
        "chance": chance_share(chosen, feats, targets, half),
        "joint_model": joint(feats, targets, half),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    top = (
        chosen[chosen["verified"]]
        .assign(a=lambda d: d["t_ver"].abs())
        .sort_values("a", ascending=False)
    )
    print(top[["feature", "target", "beta_disc", "t_disc", "beta_ver", "t_ver"]].head(30).to_string(index=False))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
