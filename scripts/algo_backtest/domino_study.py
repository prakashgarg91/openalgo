"""Run the registered domino chain test (docs/algos/domino-chain-registration.md).

Foreign driver X (known before the open) to a sector or stock's relative opening gap M, to what the
Nifty does after the open T. Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/domino_study.py <data_repo> [out_dir]
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

FOREIGN_GROUPS = (
    "us_risk",
    "us_futures",
    "fx",
    "commodities",
    "asia",
    "europe",
    "overseas_india_etfs",
)
SECTORS = [
    "_NSEBANK", "_CNXAUTO", "_CNXENERGY", "_CNXFMCG", "_CNXINFRA", "_CNXIT", "_CNXMETAL",
    "_CNXPHARMA", "_CNXPSUBANK", "_CNXREALTY",
]  # fmt: skip
STOCKS = [ctxmod.safe(s) for s in ctxmod.GROUPS["india_heavyweights"]]
END_TARGETS = ("intraday", "range")
MAX_GAP = 0.12


def relative_gaps(ctx: Path, nifty_gap: pd.Series, ist_dates: pd.DatetimeIndex) -> pd.DataFrame:
    cols = {}
    for stem in SECTORS + STOCKS:
        path = ctx / f"{stem}.csv"
        if not path.exists():
            continue
        bars = ls.load(path)
        bars = bars[(bars[["open", "close"]] > 0).all(axis=1)]
        if len(bars) < 1000:
            continue
        gap = np.log(bars["open"] / bars["close"].shift(1))
        gap.index = pd.DatetimeIndex(
            bars.index.tz_convert("Asia/Kolkata").tz_localize(None)
        ).normalize()
        gap = gap[~gap.index.duplicated(keep="last")].where(gap.abs() <= MAX_GAP)
        cols[stem] = gap.reindex(ist_dates).to_numpy() - nifty_gap.to_numpy()
    return pd.DataFrame(cols, index=ist_dates)


def stage(xs: pd.DataFrame, ys: pd.DataFrame, half: int, fdr: float = ls.Q) -> pd.DataFrame:
    rows = []
    for xn in xs.columns:
        x = xs[xn].to_numpy()
        for yn in ys.columns:
            y = ys[yn].to_numpy()
            n_d = int((~(np.isnan(x[:half]) | np.isnan(y[:half]))).sum())
            n_v = int((~(np.isnan(x[half:]) | np.isnan(y[half:]))).sum())
            if n_d < ls.MIN_OBS or n_v < ls.MIN_OBS:
                continue
            beta, t, _ = lk.ols_hac(x[:half], y[:half])
            rows.append(
                {"x": xn, "y": yn, "beta_disc": beta, "t_disc": t, "p_disc": lk.two_sided_p(t)}
            )
    table = pd.DataFrame(rows)
    table["selected"] = lk.benjamini_hochberg(table["p_disc"].to_numpy(), fdr)
    betas, ts = [], []
    for _, r in table.iterrows():
        if not r["selected"]:
            betas.append(np.nan)
            ts.append(np.nan)
            continue
        b, t, _ = lk.ols_hac(xs[r["x"]].to_numpy()[half:], ys[r["y"]].to_numpy()[half:])
        betas.append(b)
        ts.append(t)
    table["beta_ver"], table["t_ver"] = betas, ts
    table["verified"] = (
        table["selected"]
        & (np.sign(table["beta_disc"]) == np.sign(table["beta_ver"]))
        & (table["t_ver"].abs() >= ls.VERIFY_T)
    )
    return table


def chance(table: pd.DataFrame, xs: pd.DataFrame, ys: pd.DataFrame, half: int) -> dict:
    sel = table[table["selected"]]
    if sel.empty:
        return {"mean": 0.0, "p95": 0.0}
    rng = np.random.default_rng(ls.SEED)
    shares = []
    for _ in range(300):
        shuf = {c: lk.block_shuffle(ys[c].to_numpy()[half:], rng) for c in ys.columns}
        hit = 0
        for _, r in sel.iterrows():
            b, t, _ = lk.ols_hac(xs[r["x"]].to_numpy()[half:], shuf[r["y"]])
            if not np.isnan(t) and np.sign(b) == np.sign(r["beta_disc"]) and abs(t) >= ls.VERIFY_T:
                hit += 1
        shares.append(hit / len(sel))
    return {"mean": float(np.mean(shares)), "p95": float(np.quantile(shares, 0.95))}


def carried(x: np.ndarray, m: np.ndarray, t: np.ndarray) -> float:
    """t-statistic of M in a regression of T on M and X (second half), Newey-West."""
    keep = ~(np.isnan(x) | np.isnan(m) | np.isnan(t))
    x, m, t = x[keep], m[keep], t[keep]
    n = len(x)
    if n < 100:
        return float("nan")
    design = np.column_stack([np.ones(n), m, x])
    inv = np.linalg.inv(design.T @ design)
    beta = inv @ design.T @ t
    scores = design * (t - design @ beta)[:, None]
    s = scores.T @ scores
    for lag in range(1, lk.NW_LAGS + 1):
        g = scores[lag:].T @ scores[:-lag]
        s += (1 - lag / (lk.NW_LAGS + 1.0)) * (g + g.T)
    se = float(np.sqrt(max((inv @ s @ inv)[1, 1], 0.0)))
    return float(beta[1] / se) if se else float("nan")


def main() -> int:
    repo = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else repo / "research" / "domino"
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = repo / "context" / "daily"
    nifty_raw = ls.load(ctx / "_NSEI.csv")
    targets = ls.nifty_targets(nifty_raw)
    targets = targets[targets.index > ls.load(ctx / "_INDIAVIX.csv").index[0]]
    feats = ls.build_features(ctx, nifty_raw, targets.index)
    half = len(targets) // 2
    foreign = {ctxmod.safe(s) for g in FOREIGN_GROUPS for s in ctxmod.GROUPS[g]}
    xs = feats[[c for c in feats.columns if c in foreign]]
    ist = pd.DatetimeIndex(targets.index.tz_convert("Asia/Kolkata").tz_localize(None)).normalize()
    ms = relative_gaps(ctx, pd.Series(targets["gap"].to_numpy(), index=ist), ist)
    xs.index = ms.index = ist
    ts = targets[list(END_TARGETS)]
    ts.index = ist
    print(f"{len(targets)} days; {xs.shape[1]} drivers; {ms.shape[1]} middle steps")
    s1 = stage(xs, ms, half)
    s2 = stage(ms, ts, half)
    c1, c2 = chance(s1, xs, ms, half), chance(s2, ms, ts, half)
    v1, v2 = s1[s1["verified"]], s2[s2["verified"]]
    chains = []
    for _, a in v1.iterrows():
        for _, b in v2[v2["x"] == a["y"]].iterrows():
            t_med = carried(
                xs[a["x"]].to_numpy()[half:],
                ms[a["y"]].to_numpy()[half:],
                ts[b["y"]].to_numpy()[half:],
            )
            chains.append(
                {
                    "driver": a["x"], "middle": a["y"], "end": b["y"],
                    "stage1_beta": a["beta_ver"], "stage1_t": a["t_ver"],
                    "stage2_beta": b["beta_ver"], "stage2_t": b["t_ver"],
                    "indirect": a["beta_ver"] * b["beta_ver"], "mediation_t": t_med,
                    "carried": bool(abs(t_med) >= ls.VERIFY_T) if not np.isnan(t_med) else False,
                }
            )  # fmt: skip
    chain_df = pd.DataFrame(chains)
    s1.to_csv(out_dir / "stage1.csv", index=False, float_format="%.6g")
    s2.to_csv(out_dir / "stage2.csv", index=False, float_format="%.6g")
    chain_df.to_csv(out_dir / "chains.csv", index=False, float_format="%.6g")
    summary = {
        "stage1": {"tried": len(s1), "selected": int(s1["selected"].sum()), "verified": len(v1), "chance": c1},
        "stage2": {"tried": len(s2), "selected": int(s2["selected"].sum()), "verified": len(v2), "chance": c2},
        "chains": len(chain_df),
        "carried": int(chain_df["carried"].sum()) if len(chain_df) else 0,
    }  # fmt: skip
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("stage 2 verified pairs:")
    print(v2[["x", "y", "beta_disc", "t_disc", "beta_ver", "t_ver"]].to_string(index=False))
    if len(chain_df):
        top = (
            chain_df.assign(a=chain_df["indirect"].abs()).sort_values("a", ascending=False).head(15)
        )
        print(top.drop(columns="a").to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
