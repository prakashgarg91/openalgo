"""Read-only shadow ledgers for the registered ETF ideas 1 to 3 and their benchmarks.

The rules are fixed in docs/algos/idea-registration.md. This module is their code and nothing else:
it reads stored daily closes, replays each ledger from a fixed start, and returns rows. It places no
order, calls no broker and writes nothing, so the same stored closes always give the same answer.

Accounting (fixed before the first ledger day; ``VERSION`` changes if any of it changes):

- Each ledger is its own Rs 1,00,000 in cash at the start. Cash earns nothing and never goes negative.
- A signal uses closes through the previous session only. The trade it causes is made at the close of
  the next session, so a close cannot touch the holdings of that same close.
- Targets are rupee amounts. Shares are whole: floor(target value / close). Sells go first. If the
  buys plus costs exceed cash, the buys are scaled down in proportion and floored again, then one share
  at a time is removed from the largest remaining buy (ties by name) until it is affordable. Leftover
  cash stays idle.
- Costs are the itemised ``universe.Costs`` schedule (frozen as COSTS_V1). The doubled-cost variant
  doubles every component and re-runs the sizing, it does not subtract extra profit afterwards.
- Raw closes are used for trades and valuation. Splits and distributions are NOT modelled, so every
  result is labelled SHADOW and provisional until corporate-action data is added.
- Month-end means the session before the first stored session of a new calendar month. The newest stored
  session cannot be judged until the next one arrives, so that signal is acted on the day after.
- A session missing either close blocks the run (``blocked``); it is never forward-filled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, replace
from typing import Any

import pandas as pd

from services.algos.universe import Costs

VERSION = "2026-10-29-v1"
NIFTY, GOLD = "NIFTYBEES", "GOLDBEES"
CAPITAL = 100_000.0
COSTS_V1 = Costs()
DOUBLE_COSTS = replace(
    COSTS_V1,
    **{
        f.name: getattr(COSTS_V1, f.name) * 2
        for f in fields(COSTS_V1)
        if f.name not in ("gst_pct",)
    },
)

IDEAS = ("idea1", "idea2", "idea3")
BENCHMARKS = ("hold_5050", "hold_4040_cash")
MOMENTUM_DAYS = 252
TREND_DAYS = 100
IDEA1_CAP = 80_000.0
SLEEVE = 40_000.0
BAND = (0.40, 0.60)
TRIM_TOLERANCE = 1.05  # a month-end trim happens only once a position is 5 percent over its cap


def all_rules() -> tuple[str, ...]:
    """Every rule that has a ledger: ideas 1 to 3 and the twelve candidates."""
    from services.algos import etf_candidates

    return (*IDEAS, *etf_candidates.NAMES)


class Blocked(Exception):
    """Raised when the stored closes cannot be used (a session is missing one of the two closes)."""


def validate(closes: pd.DataFrame) -> pd.DataFrame:
    """Sorted closes for both ETFs on every stored session, or Blocked."""
    closes = closes[[NIFTY, GOLD]].sort_index()
    if closes.index.has_duplicates:
        raise Blocked("a session appears twice")
    gaps = closes[closes.isna().any(axis=1)]
    if not gaps.empty:
        raise Blocked(f"a close is missing on {gaps.index[0].date()}")
    if (closes <= 0).any().any():
        raise Blocked("a close is not positive")
    return closes


@dataclass
class Book:
    cash: float = CAPITAL
    shares: dict[str, int] = field(default_factory=lambda: {NIFTY: 0, GOLD: 0})
    cum_cost: float = 0.0

    def value(self, prices: dict[str, float]) -> float:
        return self.cash + sum(self.shares[s] * prices[s] for s in self.shares)


def is_month_end(closes: pd.DataFrame, i: int) -> bool:
    """True when stored session ``i`` was the last of its month, judged from session ``i + 1``."""
    return i + 1 < len(closes) and closes.index[i + 1].month != closes.index[i].month


def _returns(series: pd.Series, i: int, n: int) -> float | None:
    return None if i < n else float(series.iloc[i] / series.iloc[i - n] - 1)


def _hold_or(amount: float, symbol: str, book: Book, price: float, month_end: bool) -> float | None:
    """What to hold in ``symbol``: a rupee target, or None for no trade.

    A position that is held and whose signal is unchanged is kept as it is, so the cap is not re-bought
    every month or every day as the price moves. But the cap is a cap: at a month end a position that has
    grown more than TRIM_TOLERANCE past it is trimmed back to it, so exposure never compounds beyond what was registered.
    """
    if amount <= 0 or book.shares[symbol] == 0:
        return amount
    if month_end and book.shares[symbol] * price > amount * TRIM_TOLERANCE:
        return amount
    return None


def targets(
    idea: str, closes: pd.DataFrame, i: int, book: Book, last: bool
) -> dict[str, float] | None:
    """Rupee targets decided from closes through stored session ``i``; None means leave it as it is.

    ``last`` is True on the first execution of a ledger, when the starting allocation is bought.
    """
    from services.algos import etf_candidates

    if idea in etf_candidates.RULES:
        return etf_candidates.RULES[idea](closes, i, book, is_month_end(closes, i))
    held = {s: book.shares[s] * float(closes[s].iloc[i]) for s in (NIFTY, GOLD)}
    month_end = is_month_end(closes, i)
    if idea == "idea1":
        if not month_end:
            return None
        r = {s: _returns(closes[s], i, MOMENTUM_DAYS) for s in (NIFTY, GOLD)}
        if None in r.values():
            return None
        best = max(r, key=lambda s: (r[s], s))
        pick = best if r[best] > 0 else None
        return {
            s: _hold_or(IDEA1_CAP if s == pick else 0.0, s, book, float(closes[s].iloc[i]), True)
            for s in (NIFTY, GOLD)
        }
    if idea == "idea2":
        if i + 1 < TREND_DAYS:
            return None
        out = {}
        for s in (NIFTY, GOLD):
            average = float(closes[s].iloc[i + 1 - TREND_DAYS : i + 1].mean())
            want = SLEEVE if float(closes[s].iloc[i]) > average else 0.0
            out[s] = _hold_or(want, s, book, float(closes[s].iloc[i]), month_end)
        return out
    if idea == "idea3":
        if last:
            return {NIFTY: SLEEVE, GOLD: SLEEVE}
        if not month_end:
            return None
        invested = held[NIFTY] + held[GOLD]
        if invested <= 0:
            return None
        weight = held[NIFTY] / invested
        if BAND[0] <= weight <= BAND[1]:
            if invested <= IDEA1_CAP * TRIM_TOLERANCE:
                return None
            scale = (
                IDEA1_CAP / invested
            )  # inside the band but over the cap: trim both, keep the weights
            return {NIFTY: held[NIFTY] * scale, GOLD: held[GOLD] * scale}
        half = min(invested, IDEA1_CAP) / 2
        return {NIFTY: half, GOLD: half}
    if idea == "hold_5050":
        return {NIFTY: 50_000.0, GOLD: 50_000.0} if last else None
    if idea == "hold_4040_cash":
        return {NIFTY: SLEEVE, GOLD: SLEEVE} if last else None
    raise ValueError(f"unknown ledger {idea}")


def trade(
    book: Book, want: dict[str, float | None], prices: dict[str, float], costs: Costs
) -> tuple[float, float]:
    """Move the book to the rupee targets at ``prices``. Returns (buy notional, sell notional)."""
    sell_total = buy_total = 0.0
    want = {s: v for s, v in want.items() if v is not None}  # None: keep this holding untouched
    for s in sorted(want):
        target_shares = int(math.floor(want[s] / prices[s]))
        if target_shares < book.shares[s]:
            qty = book.shares[s] - target_shares
            notional = qty * prices[s]
            fee = costs.side(notional, buy=False, intraday=False)
            book.shares[s] -= qty
            book.cash += notional - fee
            book.cum_cost += fee
            sell_total += notional
    buys = {
        s: int(math.floor(want[s] / prices[s])) - book.shares[s]
        for s in sorted(want)
        if int(math.floor(want[s] / prices[s])) > book.shares[s]
    }

    def outlay(plan: dict[str, int]) -> float:
        return sum(
            q * prices[s] + costs.side(q * prices[s], buy=True, intraday=False)
            for s, q in plan.items()
            if q > 0
        )

    if buys and outlay(buys) > book.cash:
        factor = max(book.cash, 0.0) / outlay(buys)
        buys = {s: int(math.floor(q * factor)) for s, q in buys.items()}
        while buys and outlay(buys) > book.cash:
            largest = max(buys, key=lambda s: (buys[s] * prices[s], s))
            if buys[largest] <= 0:
                break
            buys[largest] -= 1
    for s, qty in buys.items():
        if qty <= 0:
            continue
        notional = qty * prices[s]
        fee = costs.side(notional, buy=True, intraday=False)
        book.shares[s] += qty
        book.cash -= notional + fee
        book.cum_cost += fee
        buy_total += notional
    return buy_total, sell_total


@dataclass
class Ledger:
    ledger_id: str
    cost_variant: str
    rows: pd.DataFrame


def run_ledger(
    idea: str,
    closes: pd.DataFrame,
    start: str,
    costs: Costs = COSTS_V1,
    variant: str = "base",
    matched: dict[str, float] | None = None,
) -> Ledger:
    """Replay one ledger. ``start`` is the first signal date; the first trade is the next session's close.

    ``matched`` (frozen weights of NIFTYBEES and GOLDBEES) turns this into an exposure-matched hold.
    """
    closes = validate(closes)
    first = closes.index.searchsorted(pd.Timestamp(start))
    book = Book()
    rows, peak, bought = [], CAPITAL, False
    for i in range(first + 1, len(closes)):
        prices = {s: float(closes[s].iloc[i]) for s in (NIFTY, GOLD)}
        buy_n = sell_n = 0.0
        if matched is not None:
            want = {s: CAPITAL * matched[s] for s in (NIFTY, GOLD)} if not bought else None
        else:
            want = targets(idea, closes, i - 1, book, last=not bought)
        if want is not None:
            buy_n, sell_n = trade(book, want, prices, costs)
        bought = True
        nav = book.value(prices)
        peak = max(peak, nav)
        rows.append(
            {
                "session": closes.index[i],
                "ledger_id": idea if matched is None else "hold_matched_" + idea,
                "cost_variant": variant,
                "nifty_close": prices[NIFTY],
                "gold_close": prices[GOLD],
                "nifty_shares": book.shares[NIFTY],
                "gold_shares": book.shares[GOLD],
                "cash": book.cash,
                "nav": nav,
                "nifty_weight": book.shares[NIFTY] * prices[NIFTY] / nav,
                "gold_weight": book.shares[GOLD] * prices[GOLD] / nav,
                "buy_notional": buy_n,
                "sell_notional": sell_n,
                "cumulative_cost": book.cum_cost,
                "cumulative_return": nav / CAPITAL - 1,
                "drawdown": peak - nav,
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["daily_pnl"] = frame["nav"].diff().fillna(frame["nav"] - CAPITAL)
    return Ledger(idea if matched is None else "hold_matched_" + idea, variant, frame)


def average_weights(replay: pd.DataFrame) -> dict[str, float]:
    """Mean of the post-trade marked weights over every session of a replay, inactive sessions included."""
    return {NIFTY: float(replay["nifty_weight"].mean()), GOLD: float(replay["gold_weight"].mean())}


def run_all(
    closes: pd.DataFrame, start: str, matched: dict[str, dict[str, float]] | None = None
) -> dict[str, Ledger]:
    """Every ledger in both cost variants, keyed ``<ledger>:<variant>``."""
    out: dict[str, Ledger] = {}
    for variant, costs in (("base", COSTS_V1), ("double", DOUBLE_COSTS)):
        from services.algos import etf_candidates

        for name in (*IDEAS, *BENCHMARKS, *etf_candidates.NAMES):
            out[f"{name}:{variant}"] = run_ledger(name, closes, start, costs, variant)
        for idea, weights in (matched or {}).items():
            out[f"hold_matched_{idea}:{variant}"] = run_ledger(
                idea, closes, start, costs, variant, weights
            )
    return out


def summary(ledgers: dict[str, Ledger]) -> list[dict[str, Any]]:
    """One line per ledger: last session, NAV, return, drawdown, cost, and excess over its benchmark."""
    lines = []
    for key, led in ledgers.items():
        if led.rows.empty:
            lines.append({"ledger": key, "sessions": 0})
            continue
        last = led.rows.iloc[-1]
        lines.append(
            {
                "ledger": key,
                "sessions": len(led.rows),
                "last_session": str(last["session"].date()),
                "nav": round(float(last["nav"]), 2),
                "return_pct": round(float(last["cumulative_return"]) * 100, 2),
                "drawdown": round(float(led.rows["drawdown"].max()), 2),
                "worst_day": round(float(led.rows["daily_pnl"].min()), 2),
                "cost": round(float(last["cumulative_cost"]), 2),
            }
        )
    return lines


__all__ = [
    "BENCHMARKS",
    "Blocked",
    "IDEAS",
    "Ledger",
    "VERSION",
    "average_weights",
    "run_all",
    "run_ledger",
    "summary",
    "validate",
]
