"""Cross-market linkage study: timing-safe features, a robust slope test, selection and a joint ridge.

Registered in docs/algos/linkage-study-registration.md before any result was computed. Pure
functions over frames and arrays: no database, no network, no file access, no clock.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

NIFTY_OPEN_NEWEST_HOURS = {"fx": 24, "futures": 23, "other": 9}
NW_LAGS = 5
BLOCK = 20


def session_return(bars: pd.DataFrame, kind: str = "log") -> pd.Series:
    """Per-bar return of the close: log return, or a simple difference for yields."""
    close = bars["close"].astype(float)
    if kind == "diff":
        return close.diff()
    return np.log(close).diff().replace([np.inf, -np.inf], np.nan)


def known_before(
    series: pd.Series, stamps: pd.DatetimeIndex, hours: float, opens: pd.DatetimeIndex
) -> pd.Series:
    """For each open, the value of the latest bar whose end (stamp plus ``hours``) is at or before it.

    ``series`` is indexed by bar stamp (UTC). Same-day bars that end after the open are never used.
    """
    ends = pd.DatetimeIndex(stamps) + pd.Timedelta(hours=hours)
    frame = pd.DataFrame({"end": ends, "value": series.to_numpy()}).sort_values("end")
    asked = pd.DataFrame({"open": pd.DatetimeIndex(opens)}).sort_values("open")
    merged = pd.merge_asof(asked, frame, left_on="open", right_on="end", direction="backward")
    return pd.Series(merged["value"].to_numpy(), index=asked["open"].to_numpy()).reindex(opens)


def ols_hac(x: np.ndarray, y: np.ndarray, lags: int = NW_LAGS) -> tuple[float, float, int]:
    """Slope, Newey-West t-statistic and sample size of y on x with an intercept; NaN rows dropped."""
    keep = ~(np.isnan(x) | np.isnan(y))
    x, y = x[keep], y[keep]
    n = len(x)
    if n < 30 or np.std(x) == 0:
        return float("nan"), float("nan"), n
    design = np.column_stack([np.ones(n), x])
    xtx_inv = np.linalg.inv(design.T @ design)
    beta = xtx_inv @ design.T @ y
    resid = y - design @ beta
    scores = design * resid[:, None]
    s = scores.T @ scores
    for lag in range(1, min(lags, n - 1) + 1):
        w = 1.0 - lag / (lags + 1.0)
        gamma = scores[lag:].T @ scores[:-lag]
        s += w * (gamma + gamma.T)
    cov = xtx_inv @ s @ xtx_inv
    se = float(np.sqrt(max(cov[1, 1], 0.0)))
    if se == 0:
        return float(beta[1]), float("nan"), n
    return float(beta[1]), float(beta[1] / se), n


def two_sided_p(t: float) -> float:
    return float(2 * (1 - norm.cdf(abs(t)))) if not np.isnan(t) else float("nan")


def benjamini_hochberg(pvalues: np.ndarray, q: float = 0.05) -> np.ndarray:
    """Boolean mask of the hypotheses kept at false-discovery rate ``q``; NaN p-values are never kept."""
    p = np.asarray(pvalues, dtype=float)
    ok = ~np.isnan(p)
    keep = np.zeros(len(p), dtype=bool)
    idx = np.where(ok)[0]
    if len(idx) == 0:
        return keep
    order = idx[np.argsort(p[idx])]
    m = len(order)
    passed = [i for rank, i in enumerate(order, start=1) if p[i] <= q * rank / m]
    if passed:
        cutoff = max(p[i] for i in passed)
        keep[idx[p[idx] <= cutoff]] = True
    return keep


def block_shuffle(values: np.ndarray, rng: np.random.Generator, block: int = BLOCK) -> np.ndarray:
    """Reorder consecutive blocks at random, keeping the order inside each block."""
    n = len(values)
    starts = list(range(0, n, block))
    order = rng.permutation(len(starts))
    parts = [values[starts[i] : min(starts[i] + block, n)] for i in order]
    return np.concatenate(parts)


def ridge_fit(x: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """Ridge coefficients (last entry is the intercept) on already standardised ``x``."""
    xm = np.column_stack([x, np.ones(len(x))])
    penalty = alpha * np.eye(xm.shape[1])
    penalty[-1, -1] = 0.0
    return np.linalg.solve(xm.T @ xm + penalty, xm.T @ y)


def ridge_predict(x: np.ndarray, coef: np.ndarray) -> np.ndarray:
    return np.column_stack([x, np.ones(len(x))]) @ coef


def choose_alpha(
    x: np.ndarray, y: np.ndarray, grid=(1, 10, 100, 1e3, 1e4, 1e5), folds: int = 5
) -> float:
    """Penalty with the lowest error over time-ordered, expanding-window folds inside the data given."""
    n = len(y)
    cuts = np.linspace(n * 0.4, n, folds + 1).astype(int)
    best, best_err = grid[0], np.inf
    for alpha in grid:
        err = 0.0
        for a, b in zip(cuts[:-1], cuts[1:], strict=True):
            coef = ridge_fit(x[:a], y[:a], alpha)
            err += float(np.sum((y[a:b] - ridge_predict(x[a:b], coef)) ** 2))
        if err < best_err:
            best, best_err = alpha, err
    return float(best)


def r_squared_out(y: np.ndarray, pred: np.ndarray, base_mean: float) -> float:
    """1 - squared error over the error of always predicting the discovery-half mean."""
    sst = float(np.sum((y - base_mean) ** 2))
    return float(1 - np.sum((y - pred) ** 2) / sst) if sst > 0 else float("nan")
