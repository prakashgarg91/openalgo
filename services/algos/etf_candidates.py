"""Twelve more rules for the ETF shadow ledgers, written down before any forward day (30 October 2026).

Each rule decides from closes through the previous session only; the ledger (``etf_ledger``) trades at
the next close. A rule returns rupee targets for NIFTYBEES and GOLDBEES, ``None`` for a symbol means
"leave that holding alone" and ``None`` for the whole answer means "no decision today". The accounting,
costs, month-end trimming to the cap and the benchmarks are the ledger's. Registered in
docs/algos/candidate-registration.md. Pure: no database, no network.

Every rule invests at most Rs 80,000 in total (Rs 40,000 a sleeve where two sleeves are used), the same
cap as ideas 1 to 3, so the Rs 20,000 daily limit is not at risk from exposure alone.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
import pandas as pd

from services.algos.etf_ledger import GOLD, IDEA1_CAP, NIFTY, SLEEVE, Book, _hold_or
from services.algos.universe import rsi

Rule = Callable[[pd.DataFrame, int, Book, bool], dict[str, float | None] | None]
CAP = IDEA1_CAP


def _sma(series: pd.Series, i: int, n: int) -> float | None:
    return None if i + 1 < n else float(series.iloc[i + 1 - n : i + 1].mean())


def _vol(series: pd.Series, i: int, n: int) -> float | None:
    """Annualised standard deviation of the last ``n`` daily log returns."""
    if i < n:
        return None
    returns = np.log(series.iloc[i - n : i + 1]).diff().dropna()
    return float(returns.std() * math.sqrt(252))


def _price(closes: pd.DataFrame, s: str, i: int) -> float:
    return float(closes[s].iloc[i])


def _single(closes, i, book, month_end, symbol: str, want: bool) -> dict[str, float | None]:
    out: dict[str, float | None] = {NIFTY: 0.0, GOLD: 0.0}
    out[symbol] = _hold_or(CAP if want else 0.0, symbol, book, _price(closes, symbol, i), month_end)
    other = GOLD if symbol == NIFTY else NIFTY
    out[other] = _hold_or(0.0, other, book, _price(closes, other, i), month_end)
    return out


def c01_trend200(closes, i, book, month_end):
    """Nifty ETF while it closes above its 200-day average, else cash. Judged daily."""
    avg = _sma(closes[NIFTY], i, 200)
    return (
        None
        if avg is None
        else _single(closes, i, book, month_end, NIFTY, _price(closes, NIFTY, i) > avg)
    )


def c02_cross50_200(closes, i, book, month_end):
    """Nifty ETF while its 50-day average is above its 200-day average."""
    fast, slow = _sma(closes[NIFTY], i, 50), _sma(closes[NIFTY], i, 200)
    return (
        None
        if fast is None or slow is None
        else _single(closes, i, book, month_end, NIFTY, fast > slow)
    )


def c03_absmom252(closes, i, book, month_end):
    """At a month end, Nifty ETF if its 252-day return is positive, else cash."""
    if not month_end or i < 252:
        return None
    return _single(
        closes,
        i,
        book,
        month_end,
        NIFTY,
        _price(closes, NIFTY, i) > float(closes[NIFTY].iloc[i - 252]),
    )


def c04_donchian55(closes, i, book, month_end):
    """Buy the Nifty ETF on a close above the highest close of the previous 55 sessions; sell on a close
    below the lowest close of the previous 20."""
    if i < 55:
        return None
    price = _price(closes, NIFTY, i)
    high55 = float(closes[NIFTY].iloc[i - 55 : i].max())
    low20 = float(closes[NIFTY].iloc[i - 20 : i].min())
    held = book.shares[NIFTY] > 0
    want = (price >= low20) if held else (price > high55)
    return _single(closes, i, book, month_end, NIFTY, want)


def c05_rsi2_uptrend(closes, i, book, month_end):
    """Buy the Nifty ETF when the 2-day RSI is under 10 and it is above its 200-day average; sell when the
    RSI is over 70."""
    avg = _sma(closes[NIFTY], i, 200)
    if avg is None:
        return None
    value = float(rsi(closes[NIFTY].iloc[: i + 1], 2).iloc[-1])
    held = book.shares[NIFTY] > 0
    want = (value <= 70) if held else (value < 10 and _price(closes, NIFTY, i) > avg)
    return _single(closes, i, book, month_end, NIFTY, want)


def c06_gold_trend100(closes, i, book, month_end):
    """Gold ETF while it closes above its 100-day average."""
    avg = _sma(closes[GOLD], i, 100)
    return (
        None
        if avg is None
        else _single(closes, i, book, month_end, GOLD, _price(closes, GOLD, i) > avg)
    )


def c07_voltarget(closes, i, book, month_end):
    """At a month end, Nifty ETF sized to 12 percent annual volatility: Rs 80,000 times
    min(1, 0.12 divided by its 20-day annualised volatility)."""
    vol = _vol(closes[NIFTY], i, 20)
    if not month_end or vol is None or vol <= 0:
        return None
    amount = CAP * min(1.0, 0.12 / vol)
    return {NIFTY: amount, GOLD: _hold_or(0.0, GOLD, book, _price(closes, GOLD, i), month_end)}


def c08_drawdown_filter(closes, i, book, month_end):
    """Hold the Nifty ETF; leave when it closes 10 percent or more under its 252-day high; return when it
    is back within 5 percent of that high."""
    if i < 252:
        return None
    price = _price(closes, NIFTY, i)
    ratio = price / float(closes[NIFTY].iloc[i - 251 : i + 1].max())
    held = book.shares[NIFTY] > 0
    want = (ratio > 0.90) if held else (ratio >= 0.95)
    return _single(closes, i, book, month_end, NIFTY, want)


def c09_both_trend200(closes, i, book, month_end):
    """Rs 40,000 sleeves in each ETF, each held while above its own 200-day average. Judged daily."""
    out: dict[str, float | None] = {}
    for s in (NIFTY, GOLD):
        avg = _sma(closes[s], i, 200)
        if avg is None:
            return None
        want = SLEEVE if _price(closes, s, i) > avg else 0.0
        out[s] = _hold_or(want, s, book, _price(closes, s, i), month_end)
    return out


def c10_inverse_vol(closes, i, book, month_end):
    """At a month end, Rs 80,000 split between the two ETFs in proportion to 1 divided by 60-day volatility."""
    vn, vg = _vol(closes[NIFTY], i, 60), _vol(closes[GOLD], i, 60)
    if not month_end or not vn or not vg:
        return None
    wn = (1 / vn) / (1 / vn + 1 / vg)
    return {NIFTY: CAP * wn, GOLD: CAP * (1 - wn)}


def c11_dual126(closes, i, book, month_end):
    """At a month end, the ETF with the higher 126-day return if positive, else cash. The family found in 2026."""
    if not month_end or i < 126:
        return None
    r = {s: float(closes[s].iloc[i] / closes[s].iloc[i - 126] - 1) for s in (NIFTY, GOLD)}
    best = max(r, key=lambda s: (r[s], s))
    pick = best if r[best] > 0 else None
    return {
        s: _hold_or(CAP if s == pick else 0.0, s, book, _price(closes, s, i), True)
        for s in (NIFTY, GOLD)
    }


def c12_risk_off_to_gold(closes, i, book, month_end):
    """Nifty ETF while above its 200-day average; otherwise gold ETF while above its 200-day average;
    otherwise cash. Judged daily."""
    an, ag = _sma(closes[NIFTY], i, 200), _sma(closes[GOLD], i, 200)
    if an is None or ag is None:
        return None
    if _price(closes, NIFTY, i) > an:
        pick = NIFTY
    elif _price(closes, GOLD, i) > ag:
        pick = GOLD
    else:
        pick = None
    return {
        s: _hold_or(CAP if s == pick else 0.0, s, book, _price(closes, s, i), month_end)
        for s in (NIFTY, GOLD)
    }


RULES: dict[str, Rule] = {
    "c01_trend200": c01_trend200,
    "c02_cross50_200": c02_cross50_200,
    "c03_absmom252": c03_absmom252,
    "c04_donchian55": c04_donchian55,
    "c05_rsi2_uptrend": c05_rsi2_uptrend,
    "c06_gold_trend100": c06_gold_trend100,
    "c07_voltarget": c07_voltarget,
    "c08_drawdown_filter": c08_drawdown_filter,
    "c09_both_trend200": c09_both_trend200,
    "c10_inverse_vol": c10_inverse_vol,
    "c11_dual126": c11_dual126,
    "c12_risk_off_to_gold": c12_risk_off_to_gold,
}
NAMES = tuple(RULES)
