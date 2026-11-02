"""Rejection-screen engine for the eight structures on NSE end-of-day data.

Rules, periods, costs and gates are fixed in docs/algos/eight-structure-screen-registration.md
before any run. This module is the engine only: it holds the structure definitions, the replay on
end-of-day prices, the leg-by-leg costs and the six survival gates. It does no file or network
work and has no clock. It can only say a structure is rejected or eligible for a forward test.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from services.algos.costs import REALISTIC, RealisticCosts

STEP = 50
VIX_CEILING = 20.0
MOVE_LIMIT = 0.01
SESSIONS_BEFORE = {"weekly": 2, "monthly": 5}
MIN_TRADES = {"weekly": 100, "monthly": 30}
LOSS_LIMIT = 20_000.0
BOOT_BLOCK = 3
BOOT_DRAWS = 10_000
BOOT_SEED = 20261201
BOOT_LEVEL = 0.025
MAX_SURVIVORS = 2


@dataclass(frozen=True)
class Leg:
    kind: str  # "CE" or "PE"
    offset: int  # points from the at-the-money strike
    side: int  # -1 sold, +1 bought
    far: bool = False  # the next monthly expiry after the near one (calendar only)


@dataclass(frozen=True)
class Spec:
    name: str
    cadence: str  # "weekly" or "monthly"
    legs: tuple[Leg, ...]
    move_filter: str | None  # "call": skip a fall of 1 percent; "put": skip a rise; None: VIX only


def _spread(kind: str, width: int, sign: int) -> tuple[Leg, Leg]:
    return Leg(kind, 0, -1), Leg(kind, sign * width, +1)


_CONDOR = (Leg("CE", 150, -1), Leg("CE", 400, +1), Leg("PE", -150, -1), Leg("PE", -400, +1))

SPECS: dict[str, Spec] = {
    s.name: s
    for s in (
        Spec("WC", "weekly", _spread("CE", 100, +1), "call"),
        Spec("WP", "weekly", _spread("PE", 100, -1), "put"),
        Spec("MC", "monthly", _spread("CE", 100, +1), "call"),
        Spec("MP", "monthly", _spread("PE", 100, -1), "put"),
        Spec("WK", "weekly", _CONDOR, None),
        Spec("MK", "monthly", _CONDOR, None),
        Spec("CAL", "weekly", (Leg("CE", 0, -1), Leg("CE", 0, +1, far=True)), None),
        Spec("STR", "weekly", (Leg("CE", 0, +1), Leg("PE", 0, +1)), None),
    )
}
CONTROL = "STR"


@dataclass
class Result:
    spec: str
    trades: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)


def leg_cost(
    side: int, entry: float, exit_: float, entry_day: pd.Timestamp, exit_day: pd.Timestamp,
    lot: int, c: RealisticCosts = REALISTIC,
) -> float:  # fmt: skip
    """Rupees for one leg over its round trip. Summed over the two legs of a spread it equals
    ``costs.realistic_cost`` (tested), so the screen uses the same schedule as every other test."""

    def stt(day: pd.Timestamp) -> float:
        return c.stt_after if pd.Timestamp(day) >= c.stt_change else c.stt_before

    turnover = (entry + exit_) * lot
    # STT is charged on the sale of premium: the entry for a sold leg, the exit for a bought one.
    sale = entry * lot * stt(entry_day) if side < 0 else exit_ * lot * stt(exit_day)
    brokerage = 2 * c.brokerage_per_order
    exchange = turnover * c.exchange_pct
    sebi = turnover * c.sebi_pct
    gst = c.gst * (brokerage + exchange + sebi)
    stamp = (entry if side > 0 else exit_) * lot * c.stamp_pct
    slippage = 2 * c.slip_pts * lot
    return sale + brokerage + exchange + sebi + gst + stamp + slippage


class Chain:
    """Close, settle and trading flag per (date, expiry, kind, strike) for fast lookups."""

    def __init__(self, options: pd.DataFrame):
        frame = options[options["instrument"] == "OPTIDX"].copy()
        frame["date"] = pd.to_datetime(frame["date"])
        frame["expiry"] = pd.to_datetime(frame["expiry"])
        frame["kind"] = frame["kind"].astype(str)
        self.rows: dict[tuple, tuple[float, float, int]] = {}
        self.by_day_expiry: dict[tuple, list[tuple[str, float]]] = {}
        for r in frame.itertuples(index=False):
            key = (r.date, r.expiry, r.kind, float(r.strike))
            self.rows[key] = (float(r.close), float(r.settle), int(r.contracts))
            self.by_day_expiry.setdefault((r.date, r.expiry), []).append((r.kind, float(r.strike)))
        self.sessions = [pd.Timestamp(d) for d in sorted(frame["date"].unique())]
        self.expiries = [pd.Timestamp(e) for e in sorted(frame["expiry"].unique())]

    def close(self, day, expiry, kind, strike) -> float | None:
        row = self.rows.get((pd.Timestamp(day), pd.Timestamp(expiry), kind, float(strike)))
        return row[0] if row and row[2] > 0 and row[0] > 0 else None

    def settle(self, day, expiry, kind, strike) -> float | None:
        row = self.rows.get((pd.Timestamp(day), pd.Timestamp(expiry), kind, float(strike)))
        return row[1] if row else None

    def atm(self, day, expiry) -> int | None:
        """Strike where call and put closes are closest; spot is strike plus call minus put."""
        best = None
        for kind, strike in self.by_day_expiry.get((pd.Timestamp(day), pd.Timestamp(expiry)), []):
            if kind != "CE":
                continue
            call, put = self.close(day, expiry, "CE", strike), self.close(day, expiry, "PE", strike)
            if call is None or put is None:
                continue
            gap = abs(call - put)
            if best is None or gap < best[0]:
                best = (gap, strike + call - put)
        return None if best is None else int(round(best[1] / STEP) * STEP)


def cadence_expiries(chain: Chain, cadence: str) -> list[pd.Timestamp]:
    """All stored expiries for weekly; the last expiry of each calendar month for monthly."""
    if cadence == "weekly":
        return list(chain.expiries)
    last: dict[tuple[int, int], pd.Timestamp] = {}
    for e in chain.expiries:
        last[(e.year, e.month)] = max(e, last.get((e.year, e.month), e))
    return sorted(last.values())


def simulate(
    spec: Spec,
    chain: Chain,
    nifty_close: pd.Series,
    vix_close: pd.Series,
    lot_for: Callable[[pd.Timestamp], int | None],
    first_expiry: pd.Timestamp,
    last_expiry: pd.Timestamp,
) -> Result:
    """Replay one structure over every expiry in the period. A week that cannot be priced is
    recorded with its reason and never filled in."""
    out = Result(spec.name)
    sessions = list(chain.sessions)
    position = {d: i for i, d in enumerate(sessions)}
    nifty = nifty_close.copy()
    nifty.index = pd.DatetimeIndex(nifty.index).normalize()
    vix = vix_close.copy()
    vix.index = pd.DatetimeIndex(vix.index).normalize()
    monthly = cadence_expiries(chain, "monthly")
    skip = out.skipped
    for expiry in cadence_expiries(chain, spec.cadence):
        if not (pd.Timestamp(first_expiry) <= expiry <= pd.Timestamp(last_expiry)):
            continue
        why = lambda reason, e=expiry: skip.append({"expiry": e, "reason": reason})  # noqa: E731
        lot = lot_for(expiry)
        if lot is None:
            why("no documented lot size")
            continue
        if expiry not in position:
            why("expiry session not stored")
            continue
        at = position[expiry] - SESSIONS_BEFORE[spec.cadence]
        if at < 1:
            why("entry session not stored")
            continue
        day, prev = sessions[at], sessions[at - 1]
        level = vix.get(day)
        if level is None or pd.isna(level):
            why("no vix")
            continue
        if float(level) >= VIX_CEILING:
            why("vix ceiling")
            continue
        move = None
        if spec.move_filter:
            a, b = nifty.get(day), nifty.get(prev)
            if a is None or b is None or pd.isna(a) or pd.isna(b):
                why("no nifty close")
                continue
            move = float(a) / float(b) - 1
            if (spec.move_filter == "call" and move <= -MOVE_LIMIT) or (
                spec.move_filter == "put" and move >= MOVE_LIMIT
            ):
                why("one-day move filter")
                continue
        atm = chain.atm(day, expiry)
        if atm is None:
            why("no at-the-money strike")
            continue
        legs, priced = [], True
        for leg in spec.legs:
            leg_expiry = expiry
            if leg.far:
                later = [m for m in monthly if m > expiry]
                if not later:
                    priced = False
                    break
                leg_expiry = later[0]
            strike = atm + leg.offset
            entry = chain.close(day, leg_expiry, leg.kind, strike)
            if entry is None:
                priced = False
                break
            legs.append({"kind": leg.kind, "strike": strike, "side": leg.side, "expiry": leg_expiry,
                         "far": leg.far, "entry": entry})  # fmt: skip
        if not priced:
            why("a leg has no trade at the entry close")
            continue
        for g in legs:
            if g["far"]:
                px = chain.close(expiry, g["expiry"], g["kind"], g["strike"])
            else:
                px = chain.settle(expiry, expiry, g["kind"], g["strike"])
            if px is None:
                priced = False
                break
            g["exit"] = px
        if not priced:
            why("a leg has no price on the expiry date")
            continue
        pts = sum(g["side"] * (g["exit"] - g["entry"]) for g in legs)
        cost = sum(leg_cost(g["side"], g["entry"], g["exit"], day, expiry, lot) for g in legs)
        out.trades.append(
            {"structure": spec.name, "expiry": expiry, "entry": day, "exit": expiry, "lot": lot,
             "legs": legs, "pts": pts, "cost": cost, "net": pts * lot - cost,
             "net_2x": pts * lot - 2 * cost, "marks": _marks(chain, legs, day, expiry, sessions, lot)}
        )  # fmt: skip
    return out


def _marks(chain: Chain, legs: list[dict], entry: pd.Timestamp, expiry: pd.Timestamp,
           sessions: list, lot: int) -> dict[pd.Timestamp, float]:  # fmt: skip
    """Rupee mark of the open position at each session's close, carrying the last known close."""
    last = {i: g["entry"] for i, g in enumerate(legs)}
    marks: dict[pd.Timestamp, float] = {}
    for d in sessions:
        if d < entry or d > expiry:
            continue
        total = 0.0
        for i, g in enumerate(legs):
            if d == expiry:
                px = g["exit"]
            else:
                px = chain.close(d, g["expiry"], g["kind"], g["strike"])
                px = last[i] if px is None else px
            last[i] = px
            total += g["side"] * (px - g["entry"])
        marks[d] = total * lot
    return marks


def equity(trades: list[dict], sessions: list) -> pd.Series:
    """Marked-to-market equity from zero at each session's close: closed nets plus open marks."""
    days = sorted(pd.Timestamp(d) for d in sessions)
    values = []
    for day in days:
        total = 0.0
        for t in trades:
            if t["exit"] <= day:
                total += t["net"]
            elif t["entry"] <= day:
                known = [d for d in t["marks"] if d <= day]
                if known:
                    total += t["marks"][max(known)]
        values.append(total)
    return pd.Series(values, index=pd.DatetimeIndex(days), dtype=float)


def drawdown(eq: pd.Series) -> float:
    if eq.empty:
        return 0.0
    peak = np.maximum.accumulate(np.r_[0.0, eq.to_numpy()])[1:]
    return float((peak - eq.to_numpy()).max())


def worst_day(eq: pd.Series) -> float:
    if eq.empty:
        return 0.0
    return float(np.diff(np.r_[0.0, eq.to_numpy()]).min())


def bootstrap_lower(values: np.ndarray, level: float = BOOT_LEVEL) -> float:
    """Lower bound of the mean from a moving-block bootstrap over trades (fixed block and seed)."""
    n = len(values)
    if n == 0:
        return float("nan")
    block = min(BOOT_BLOCK, n)
    rng = np.random.default_rng(BOOT_SEED)
    starts = rng.integers(0, n - block + 1, size=(BOOT_DRAWS, -(-n // block)))
    picked = values[(starts[:, :, None] + np.arange(block)).reshape(BOOT_DRAWS, -1)[:, :n]]
    return float(np.quantile(picked.mean(axis=1), level))


def evaluate(
    result: Result, cadence: str, sessions: list, min_trades: int | None = None
) -> dict[str, Any]:
    """The six survival gates and the numbers behind them. Verdicts are only eligible or rejected."""
    trades = sorted(result.trades, key=lambda t: t["entry"])
    nets = np.array([t["net"] for t in trades], dtype=float)
    nets2 = np.array([t["net_2x"] for t in trades], dtype=float)
    eq = equity(trades, sessions)
    half = len(trades) // 2
    first, second = nets[:half], nets[half:]
    stats = {
        "trades": len(trades),
        "not_counted": dict(Counter(s["reason"] for s in result.skipped)),
        "net": float(nets.sum()) if len(nets) else 0.0,
        "net_2x": float(nets2.sum()) if len(nets2) else 0.0,
        "drawdown": drawdown(eq),
        "worst_day": worst_day(eq),
        "net_without_best": float(nets.sum() - nets.max()) if len(nets) else 0.0,
        "net_first_half": float(first.sum()) if len(first) else 0.0,
        "net_second_half": float(second.sum()) if len(second) else 0.0,
        "boot_lower_mean": bootstrap_lower(nets),
    }
    gates = {
        "enough_trades": stats["trades"] >= (min_trades or MIN_TRADES[cadence]),
        "net_positive_at_both_costs": stats["net"] > 0 and stats["net_2x"] > 0,
        "drawdown_and_worst_day_within_limit": stats["drawdown"] <= LOSS_LIMIT
        and stats["worst_day"] >= -LOSS_LIMIT,
        "positive_without_best_trade": stats["trades"] > 0 and stats["net_without_best"] > 0,
        "positive_in_each_half": stats["net_first_half"] > 0 and stats["net_second_half"] > 0,
        "bootstrap_bound_above_zero": bool(stats["boot_lower_mean"] > 0),
    }
    verdict = "eligible for a forward test" if all(gates.values()) else "rejected"
    return {"stats": stats, "gates": gates, "verdict": verdict}


def choose_survivors(reports: dict[str, dict[str, Any]]) -> list[str]:
    """At most two structures go forward: smallest worst drawdown first, ties by larger net.
    The control never goes forward, and if it passes the whole screen is suspect."""
    eligible = [
        n
        for n, r in reports.items()
        if r["verdict"] == "eligible for a forward test" and n != CONTROL
    ]
    eligible.sort(key=lambda n: (reports[n]["stats"]["drawdown"], -reports[n]["stats"]["net"]))
    return eligible[:MAX_SURVIVORS]


def control_is_suspect(reports: dict[str, dict[str, Any]]) -> bool:
    """The long straddle is expected to lose; if it passes every gate, stop and look at the data."""
    return CONTROL in reports and reports[CONTROL]["verdict"] == "eligible for a forward test"
