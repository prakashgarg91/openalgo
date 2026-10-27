"""Pricing and calendar helpers shared by the algo backtests."""

import math
from datetime import timedelta

import pandas as pd

RISK_FREE = 0.065


def num(x):
    """A float, or None for a missing value."""
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, sig, kind):
    """Black-Scholes price of a European option; T in years."""
    if T <= 0 or sig <= 0:
        return max(S - K, 0) if kind == "CE" else max(K - S, 0)
    d1 = (math.log(S / K) + (RISK_FREE + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if kind == "CE":
        return S * ncdf(d1) - K * math.exp(-RISK_FREE * T) * ncdf(d2)
    return K * math.exp(-RISK_FREE * T) * ncdf(-d2) - S * ncdf(-d1)


def expiry_after(t):
    """Nearest weekly expiry on or after t: Thursday, or Tuesday since Sep 2025."""
    weekday = 1 if t >= pd.Timestamp("2025-09-01") else 3
    return t + timedelta(days=(weekday - t.weekday()) % 7)
