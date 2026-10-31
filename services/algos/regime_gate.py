"""Range-group gate for the regime-gated spread test (docs/algos/regime-spread-registration.md).

The model is the baseline of the range study: ln India VIX of the previous session and the Nifty's
range of the previous session predict ln(range) of the day. Coefficients and the five group cut
points are fitted on the days up to FIT_END only and are then frozen. Pure functions over frames:
no database, no network, no file access.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.algos import linkage as lk
from services.algos.intraday import OptionBars

FIT_END = pd.Timestamp("2017-07-10")
GROUPS = 5


def range_frame(nifty: pd.DataFrame, vix: pd.DataFrame) -> pd.DataFrame:
    """Per Nifty day (India date): ln range of the day, ln India VIX of the previous session, previous range.

    Both inputs are UTC-indexed daily bars with open, high, low and close.
    """
    nifty = nifty[(nifty[["open", "high", "low", "close"]] > 0).all(axis=1)]
    vix = vix[vix["close"] > 0]
    rng = (nifty["high"] - nifty["low"]) / nifty["open"]
    frame = pd.DataFrame(index=nifty.index)
    frame["target"] = np.log(rng)
    frame["range_1"] = rng.shift(1)
    frame["vix_prev"] = lk.known_before(np.log(vix["close"]), vix.index, 9, nifty.index).to_numpy()
    frame.index = pd.DatetimeIndex(
        frame.index.tz_convert("Asia/Kolkata").tz_localize(None)
    ).normalize()
    return frame.replace([np.inf, -np.inf], np.nan)


def fit(frame: pd.DataFrame, fit_end: pd.Timestamp = FIT_END) -> tuple[np.ndarray, np.ndarray]:
    """(coefficients, four cut points) from the days up to ``fit_end``."""
    used = frame[frame.index <= fit_end].dropna()
    x = used[["vix_prev", "range_1"]].to_numpy()
    coef = lk.ridge_fit(x, used["target"].to_numpy(), 1e-9)
    cuts = np.quantile(lk.ridge_predict(x, coef), [0.2, 0.4, 0.6, 0.8])
    return coef, cuts


def groups(frame: pd.DataFrame, coef: np.ndarray, cuts: np.ndarray) -> pd.Series:
    """Range group 1 (lowest predicted) to 5 (highest) per day; days with missing inputs are left out."""
    ok = frame.dropna(subset=["vix_prev", "range_1"])
    pred = lk.ridge_predict(ok[["vix_prev", "range_1"]].to_numpy(), coef)
    return pd.Series(np.searchsorted(cuts, pred) + 1, index=ok.index)


GATES = {
    "none": lambda g: True,
    "not5": lambda g: g != 5,
    "g123": lambda g: g <= 3,
    "g12": lambda g: g <= 2,
}


class GatedBars(OptionBars):
    """The same option bars, offering only the days inside a date window that a gate allows."""

    def __init__(self, base: OptionBars, allowed: set[pd.Timestamp]):
        self.__dict__.update(base.__dict__)
        self._allowed = {pd.Timestamp(d).normalize() for d in allowed}

    def days(self) -> list[pd.Timestamp]:
        return [d for d in super().days() if d in self._allowed]
