"""Range-group gate: frozen fit, group assignment and the day filter."""

import numpy as np
import pandas as pd

from services.algos import regime_gate as rg
from services.algos.intraday import OptionBars


def daily(n=900, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-01-04", periods=n, freq="B", tz="UTC") + pd.Timedelta(
        hours=3, minutes=45
    )
    close = 5000 * np.exp(np.cumsum(rng.normal(0, 0.008, n)))
    span = np.abs(rng.normal(0.012, 0.004, n)) * close
    nifty = pd.DataFrame(
        {"open": close, "high": close + span, "low": close - span / 2, "close": close}, index=idx
    )
    vix = pd.DataFrame({"open": 18.0, "close": 18 + rng.normal(0, 2, n)}, index=idx)
    return nifty, vix


def test_groups_cover_one_to_five_and_the_fit_ignores_later_days():
    nifty, vix = daily()
    frame = rg.range_frame(nifty, vix)
    cutoff = frame.index[400]
    coef, cuts = rg.fit(frame, cutoff)
    later = frame.copy()
    later.loc[later.index > cutoff, "target"] = 99.0  # nothing after the fit date may matter
    coef2, cuts2 = rg.fit(later, cutoff)
    assert np.allclose(coef, coef2) and np.allclose(cuts, cuts2)
    g = rg.groups(frame, coef, cuts)
    assert set(g.unique()) == {1, 2, 3, 4, 5}


def test_gates_are_nested():
    assert [g for g in range(1, 6) if rg.GATES["g12"](g)] == [1, 2]
    assert [g for g in range(1, 6) if rg.GATES["g123"](g)] == [1, 2, 3]
    assert [g for g in range(1, 6) if rg.GATES["not5"](g)] == [1, 2, 3, 4]
    assert all(rg.GATES["none"](g) for g in range(1, 6))


def test_gated_bars_offers_only_allowed_days():
    idx = pd.date_range("2025-01-01 09:15", periods=3, freq="5min").append(
        pd.date_range("2025-01-02 09:15", periods=3, freq="5min")
    )
    frame = pd.DataFrame(dict.fromkeys(("open", "high", "low", "close"), 1.0), index=idx)
    base = OptionBars({(pd.Timestamp("2025-01-07"), "CE", 25000.0): frame})
    gated = rg.GatedBars(base, {pd.Timestamp("2025-01-02")})
    assert gated.days() == [pd.Timestamp("2025-01-02")]
    assert base.days() == [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02")]
