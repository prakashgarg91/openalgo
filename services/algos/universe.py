"""Strategies beyond option spreads, run on daily bars of exchange-traded funds.

For a small account (Rs 1,00,000 with a Rs 20,000 daily loss limit) the choices are not only Zen-style
option spreads. This module holds the other families, as plain rules on daily bars of a Nifty ETF and a
gold ETF, with cash earning a fixed yield when nothing is held:

- trend filter: hold the ETF while it is above its moving average, else cash
- dual momentum: each month hold what rose over the last L days, else cash
- short-term mean reversion: buy a sharp dip inside an uptrend, sell the bounce
- seasonal rules: turn of the month, or one weekday

Gap and overnight rules are not offered: they need the opening price, and the free ETF opening prints are
unreliable (an open of 146 on a day that closed at 126), so a test of them would measure data errors.

Rules the rest of the module keeps:

- A signal uses only data up to the close of its own day and is executed at the CLOSE of the next day, a
  full day of delay, using closing prices only. Tests check no signal sees a later price.
- Every trade pays itemised costs (brokerage, exchange, stamp, tax, depository, slippage); idle cash earns a
  fixed yield; the account is simulated one day at a time so the worst day can be compared with the cap.
- No stock selection from today's index lists: that would be survivorship bias, which flatters every
  result, so it is not offered.

Pure: prices come in as DataFrames, results go out as lists of ``{"date", "pnl"}`` on a fixed base.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

CASH_YIELD = 0.06  # assumed annual return on idle cash (overnight or liquid fund)
TRADING_DAYS = 252
BASE = 100_000.0


# -- costs -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Costs:
    """Itemised charges as assumed here. They are assumptions: check them against your broker's tariff."""

    brokerage: float = 20.0  # rupees per order
    exchange_pct: float = 0.00345 / 100
    sebi_pct: float = 0.0001 / 100
    gst_pct: float = 18.0 / 100  # on brokerage and exchange charges
    stamp_buy_pct: float = 0.015 / 100  # delivery buy
    stt_sell_delivery_pct: float = 0.001 / 100  # equity ETF units sold on the exchange
    stt_sell_intraday_pct: float = 0.025 / 100
    stamp_buy_intraday_pct: float = 0.003 / 100
    depository: float = 15.34  # per scrip sold from delivery, plus GST
    slippage_pct: float = 0.05 / 100  # per side: the gap between quote and fill on a liquid ETF

    def side(self, notional: float, *, buy: bool, intraday: bool) -> float:
        if notional <= 0:
            return 0.0
        charges = self.brokerage + notional * (self.exchange_pct + self.sebi_pct)
        total = charges * (1 + self.gst_pct) + notional * self.slippage_pct
        if buy:
            total += notional * (self.stamp_buy_intraday_pct if intraday else self.stamp_buy_pct)
        else:
            total += notional * (
                self.stt_sell_intraday_pct if intraday else self.stt_sell_delivery_pct
            )
            if not intraday:
                total += self.depository * (1 + self.gst_pct)
        return total


DEFAULT_COSTS = Costs()


# -- indicators ------------------------------------------------------------------------------------


def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=n).mean()


def rsi(series: pd.Series, n: int = 2) -> pd.Series:
    """Wilder's relative strength index. Uses only the current and earlier closes."""
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop days whose closing price is far from its neighbours: a bad print, however many days it lasts.

    A fund cannot trade at a tenth of its price for two days, so a close more than 35 percent away from
    the median of the eleven closes around it is an error in the data, not a market move. Opening prices
    are not used anywhere, because they are not reliable.
    """
    df = df[df["Close"] > 0].dropna(subset=["Close"]).copy()
    median = df["Close"].rolling(11, center=True, min_periods=5).median()
    bad = (df["Close"] / median - 1).abs() > 0.35
    return df[~bad.fillna(False)]


# -- strategy specs --------------------------------------------------------------------------------

FAMILIES = ("trend", "dual_momentum", "mean_reversion", "seasonal")


@dataclass(frozen=True)
class Strategy:
    family: str
    params: tuple[tuple[str, Any], ...]

    @property
    def p(self) -> dict[str, Any]:
        return dict(self.params)

    @property
    def name(self) -> str:
        inner = ", ".join(f"{k}={v}" for k, v in self.params)
        return f"{self.family}({inner})"

    def to_dict(self) -> dict[str, Any]:
        return {"family": self.family, **self.p}


def strat(family: str, **params: Any) -> Strategy:
    return Strategy(family, tuple(sorted(params.items())))


def grid() -> list[Strategy]:
    """The whole search space, fixed up front. Its size is reported with every result."""
    out: list[Strategy] = [strat("trend", n=n) for n in (50, 100, 150, 200)]
    out += [
        strat("dual_momentum", lookback=lb, mode=m)
        for lb in (63, 126, 252)
        for m in ("best", "all")
    ]
    out += [strat("mean_reversion", entry=e, exit=x) for e in (5, 10, 20) for x in (50, 70)]
    out += [strat("seasonal", kind="turn_of_month", span=s) for s in (3, 5)]
    out += [strat("seasonal", kind="weekday", day=d) for d in range(5)]
    return out


# -- turning a rule into positions ----------------------------------------------------------------
#
# Every function returns, for each day t, the position taken at the close of day t on a signal from the close
# of day t-1 (``shift(1)``). It then earns the return to the close of day t+1.


def _month_end_flags(index: pd.DatetimeIndex) -> pd.Series:
    month = pd.Series(index.to_period("M"), index=index)
    return month != month.shift(
        -1
    )  # last trading day of its month (the final day is judged by the caller)


def held_trend(bars: dict[str, pd.DataFrame], n: int) -> pd.DataFrame:
    close = bars["equity"]["Close"]
    signal = (close > sma(close, n)).astype(float)
    return pd.DataFrame({"equity": signal.shift(1).fillna(0.0), "gold": 0.0}, index=close.index)


def held_dual_momentum(bars: dict[str, pd.DataFrame], lookback: int, mode: str) -> pd.DataFrame:
    close = pd.DataFrame({k: bars[k]["Close"] for k in ("equity", "gold")}).dropna()
    ret = close / close.shift(lookback) - 1
    is_end = _month_end_flags(close.index)
    target = pd.DataFrame(0.0, index=close.index, columns=["equity", "gold"])
    current = pd.Series(0.0, index=close.columns)
    for i in range(len(close.index)):
        if is_end.iloc[i] and not ret.iloc[i].isna().any():
            r = ret.iloc[i]
            positive = r[r > 0]
            current = pd.Series(0.0, index=close.columns)
            if len(positive):
                if mode == "best":
                    current[positive.idxmax()] = 1.0
                else:
                    current[positive.index] = 1.0 / len(positive)
        target.iloc[i] = current.values
    return target.shift(1).fillna(0.0)


def held_mean_reversion(bars: dict[str, pd.DataFrame], entry: float, exit: float) -> pd.DataFrame:
    close = bars["equity"]["Close"]
    r2, trend = rsi(close, 2), sma(close, 200)
    state, days_in, signal = 0.0, 0, []
    for c, r, t in zip(close, r2, trend, strict=True):
        if state == 0.0:
            if not np.isnan(r) and not np.isnan(t) and r < entry and c > t:
                state, days_in = 1.0, 0
        else:
            days_in += 1
            if r > exit or days_in >= 5:
                state = 0.0
        signal.append(state)
    sig = pd.Series(signal, index=close.index)
    return pd.DataFrame({"equity": sig.shift(1).fillna(0.0), "gold": 0.0}, index=close.index)


def held_seasonal(
    bars: dict[str, pd.DataFrame], kind: str, span: int = 0, day: int = 0
) -> pd.DataFrame:
    close = bars["equity"]["Close"]
    idx = close.index
    if kind == "weekday":
        # Held during the chosen weekday, decided the evening before (it is a calendar fact, not a forecast).
        held = pd.Series((idx.dayofweek == day).astype(float), index=idx)
    else:
        month = pd.Series(idx.to_period("M"), index=idx)
        pos_from_end = month.groupby(month).cumcount(
            ascending=False
        )  # 0 on a month's last trading day
        pos_from_start = month.groupby(month).cumcount()
        in_window = (pos_from_end < 2) | (pos_from_start < span)
        held = in_window.astype(float)
    return pd.DataFrame({"equity": held, "gold": 0.0}, index=idx)


# -- the account, one day at a time ---------------------------------------------------------------


def _cash_day() -> float:
    # Results are on a fixed base (not compounded), so the daily interest is the simple share of a year.
    return CASH_YIELD / TRADING_DAYS


def run(
    strategy: Strategy, bars: dict[str, pd.DataFrame], costs: Costs = DEFAULT_COSTS
) -> list[dict[str, Any]]:
    """Daily rupee result on a Rs 1,00,000 base, including cash interest and every charge."""
    eq = bars["equity"]
    idx = eq.index
    cash_r = _cash_day()
    pnl = np.zeros(len(idx))
    family, p = strategy.family, strategy.p

    if family == "trend":
        held = held_trend(bars, p["n"])
    elif family == "dual_momentum":
        held = held_dual_momentum(bars, p["lookback"], p["mode"]).reindex(idx).fillna(0.0)
    elif family == "mean_reversion":
        held = held_mean_reversion(bars, p["entry"], p["exit"])
    else:
        held = held_seasonal(bars, p["kind"], p.get("span", 0), p.get("day", 0))

    closes = {k: bars[k]["Close"].reindex(idx).ffill() for k in ("equity", "gold")}
    prev = {"equity": 0.0, "gold": 0.0}
    for t in range(len(idx) - 1):
        w = {k: float(held[k].iloc[t]) for k in ("equity", "gold")}
        # Return earned from the close of day t to the close of day t+1 on what is held from day t.
        # ``held`` is the signal of day t-1, so the trade happens a full day after the signal.
        invested = 0.0
        for k in ("equity", "gold"):
            r = closes[k].iloc[t + 1] / closes[k].iloc[t] - 1
            pnl[t] += w[k] * BASE * (0.0 if np.isnan(r) else r)
            invested += w[k]
            delta = w[k] - prev[k]  # traded at the close of day t
            if abs(delta) > 1e-9:
                pnl[t] -= costs.side(abs(delta) * BASE, buy=delta > 0, intraday=False)
        pnl[t] += BASE * max(0.0, 1.0 - invested) * cash_r
        prev = w
    return [
        {"date": d.strftime("%Y-%m-%d"), "pnl": float(x)} for d, x in zip(idx, pnl, strict=True)
    ]


def buy_and_hold(
    bars: dict[str, pd.DataFrame], key: str = "equity", costs: Costs = DEFAULT_COSTS
) -> list[dict[str, Any]]:
    """Buy at the first close, hold: the bar every timing rule has to clear."""
    df = bars[key]
    c = df["Close"].to_numpy()
    pnl = np.zeros(len(df))
    for t in range(len(df) - 1):
        pnl[t] = BASE * (c[t + 1] / c[t] - 1)
    pnl[0] -= costs.side(BASE, buy=True, intraday=False)
    return [
        {"date": d.strftime("%Y-%m-%d"), "pnl": float(x)}
        for d, x in zip(df.index, pnl, strict=True)
    ]


def cash_only(index: pd.DatetimeIndex) -> list[dict[str, Any]]:
    return [{"date": d.strftime("%Y-%m-%d"), "pnl": BASE * _cash_day()} for d in index]


# -- judging a rule ------------------------------------------------------------------------------


def stats(days: list[dict[str, Any]]) -> dict[str, Any]:
    """Return, deepest fall, worst day for a stretch of daily results on the Rs 1,00,000 base."""
    if not days:
        return {"days": 0, "total": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "worst_day": 0.0}
    pnl = np.array([d["pnl"] for d in days])
    equity = BASE + np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate([[BASE], equity]))[1:]
    years = len(pnl) / TRADING_DAYS
    final = max(equity[-1], 1.0)
    return {
        "days": int(len(pnl)),
        "total": round(float(pnl.sum()), 1),
        "cagr": round(float((final / BASE) ** (1 / years) - 1) * 100, 2) if years > 0 else 0.0,
        "max_drawdown": round(float((equity - peak).min()), 1),
        "worst_day": round(float(pnl.min()), 1),
    }


# -- the search ----------------------------------------------------------------------------------
#
# Fixed before any result was seen. Every rule is judged against two bars an investor already has:
# leaving the money as cash, and buying the Nifty ETF and holding it.

TRAIN_SHARE, VALIDATE_SHARE = 0.50, 0.25
TOP_ON_TRAIN = 5
DRAWDOWN_WEIGHT = 0.5
WARMUP = (
    250  # trading days every rule needs before its first signal, so all are judged on the same days
)
RISK_CUT = 0.30  # "lowers risk": a deepest fall at least 30 percent shallower than buy and hold
RISK_RETURN_FLOOR = 0.75  # ... while keeping at least 75 percent of its yearly return
DAILY_CAP = 20_000.0


def _bounds(dates: list[str]) -> dict[str, tuple[str, str]]:
    n = len(dates)
    a, b = int(n * TRAIN_SHARE), int(n * (TRAIN_SHARE + VALIDATE_SHARE))
    return {
        "train": (dates[0], dates[a - 1]),
        "validate": (dates[a], dates[b - 1]),
        "test": (dates[b], dates[-1]),
    }


def _slice(days: list[dict[str, Any]], lo: str, hi: str) -> list[dict[str, Any]]:
    return [d for d in days if lo <= d["date"] <= hi]


def _excess(days: list[dict[str, Any]], cash: list[dict[str, Any]], lo: str, hi: str) -> float:
    return sum(d["pnl"] for d in _slice(days, lo, hi)) - sum(d["pnl"] for d in _slice(cash, lo, hi))


def _score(days, cash, lo, hi) -> float:
    return (
        _excess(days, cash, lo, hi) + DRAWDOWN_WEIGHT * stats(_slice(days, lo, hi))["max_drawdown"]
    )


def verdict(
    winner_test: dict, winner_val_excess: float, test_excess: float, bh_test: dict
) -> dict[str, Any]:
    earns = winner_val_excess > 0 and test_excess > 0
    beats = winner_test["cagr"] >= bh_test["cagr"]
    lowers = (
        bh_test["max_drawdown"] < 0
        and winner_test["max_drawdown"] >= (1 - RISK_CUT) * bh_test["max_drawdown"]
        and winner_test["cagr"] >= RISK_RETURN_FLOOR * bh_test["cagr"]
    )
    within_cap = winner_test["worst_day"] >= -DAILY_CAP
    shown = earns and (beats or lowers) and within_cap
    reasons = []
    if not earns:
        reasons.append("It did not beat leaving the money in cash on both later periods.")
    elif not (beats or lowers):
        reasons.append(
            "It earned more than cash but neither beat buy and hold nor cut its deepest fall enough."
        )
    if not within_cap:
        reasons.append("A day lost more than the daily limit.")
    return {
        "edge_shown": shown,
        "beats_cash": earns,
        "beats_buy_and_hold": beats,
        "lowers_risk_like_buy_and_hold": lowers,
        "within_daily_cap": within_cap,
        "headline": (
            "It held up on data it was not chosen on. That is one test period, not proof."
            if shown
            else "No edge shown over leaving the money in cash or buying and holding."
        ),
        "reasons": reasons,
    }


def search(
    bars: dict[str, pd.DataFrame],
    strategies: list[Strategy] | None = None,
    costs: Costs = DEFAULT_COSTS,
) -> dict[str, Any]:
    strategies = strategies if strategies is not None else grid()
    index = bars["equity"].index
    ran = {s: run(s, bars, costs)[WARMUP:] for s in strategies}
    bh = buy_and_hold(bars, "equity", costs)[WARMUP:]
    cash = cash_only(index)[WARMUP:]
    dates = [d["date"] for d in cash]
    seg = _bounds(dates)
    rows = []
    for s, days in ran.items():
        rows.append(
            {
                "strategy": s,
                "train_score": _score(days, cash, *seg["train"]),
                "validate_score": _score(days, cash, *seg["validate"]),
                "stats": {k: stats(_slice(days, *seg[k])) for k in seg},
                "excess": {k: _excess(days, cash, *seg[k]) for k in seg},
            }
        )
    top = sorted(rows, key=lambda r: r["train_score"], reverse=True)[:TOP_ON_TRAIN]
    winner = max(top, key=lambda r: r["validate_score"])
    bh_stats = {k: stats(_slice(bh, *seg[k])) for k in seg}
    return {
        "trials": len(strategies),
        "segments": {k: list(v) for k, v in seg.items()},
        "lost_to_cash_on_test": sum(1 for r in rows if r["excess"]["test"] < 0),
        "baselines": {
            "buy_and_hold": bh_stats,
            "cash": {k: stats(_slice(cash, *seg[k])) for k in seg},
        },
        "rows": rows,
        "winner": winner,
        "verdict": verdict(
            winner["stats"]["test"],
            winner["excess"]["validate"],
            winner["excess"]["test"],
            bh_stats["test"],
        ),
        "winner_days": ran[winner["strategy"]],
        "buy_and_hold_days": bh,
    }
