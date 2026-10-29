"""Forward shadow test of three registered side rules on captured 1-minute candles.

The rules, the filters and the pass gates are fixed in docs/algos/forward-test-registration.md
before any day of this test is seen. This module is the code of that page and nothing else: it
reads candles that are already stored, replays the frozen entry and exit machine for each rule,
and returns trades. It places no order, calls no broker and writes nothing, so the same stored
days always give the same answer and the three rules stay three independent accounts.

How a day is replayed (all of it fixed by the registration):

- The side is decided at 10:15 from three numbers: P, the close of the 10:14 Nifty minute
  candle; O, the open of the 09:15 candle; and V, the previous session's last close. A missing
  number means no entry, and the reason is counted.
- A: sell a put spread when P is above both O and V, otherwise a call spread.
  B: sell a put spread when P is at or below O, otherwise a call spread.
  C: always a call spread. C is the control and is never promoted.
- Filters are read once, at the first entry of a day: no entry when the previous session's India
  VIX closed at 20 or higher, or when P is 1 percent or more under V. They do not apply to a
  reversal.
- The spread is sold at the money (P rounded to 50) and bought 400 points away, on the nearest
  weekly expiry, which on expiry day is that day. The entry fills at the open of the 10:15 candle.
- Exits are the replay that reproduced Zen's published exits (``intraday.walk_position``): the
  spread stops when its value rises 43.8 points over the credit (pessimistic high, 2 points of
  slip), takes profit when its closing value is 10 points or less (remaining value, not profit
  taken), and otherwise leaves at 15:00 the next session or at expiry. A stop before 14:30 reverses
  to the other side at the next minute, up to 3 times, with the same exits. A position held
  overnight blocks the next entry.
- Fills are candle prices, not bids and asks, so results stay provisional. A candle that could
  hold both a stop and a target takes the stop.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import time as dtime
from typing import Any

import numpy as np
import pandas as pd

from services.algos import intraday, lab
from services.algos.intraday import OptionBars, Rules

VERSION = "2026-10-29-v1"
STEP = pd.Timedelta(minutes=1)
SIDE_RULES = ("A", "B", "C")
CANDIDATES = ("A", "B")
CONTROL = "C"

REGISTERED = Rules(
    width=400,
    entry_time="10:15",
    exit_time="15:00",
    stop_pts=43.8,
    stop_slip_pts=2.0,
    target_pts=10.0,
    reverse=True,
    max_reversals=3,
    reverse_until="14:30",
    side_rule="registered",
    vix_ceiling=20.0,
    gap_floor=-0.01,
    max_dte=8,
)

MIN_EPISODES = 100
REGISTERED_SESSIONS = 252
MIN_NET = 10_000.0
MAX_DRAWDOWN = 20_000.0
DAILY_CAP = 20_000.0
BOOTSTRAP_BLOCK = 5
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 20261029
BOOTSTRAP_LEVEL = 0.025


def replace_rules(**changes: Any) -> Rules:
    """The registered rules with some fields changed, for tests only; a real run uses REGISTERED."""
    from dataclasses import replace

    return replace(REGISTERED, **changes)


def choose_side(rule: str, p: float, o: float, v: float) -> str:
    """CE (sell a call spread) or PE (sell a put spread) for rule A, B or C."""
    if rule == "A":
        return "PE" if p > o and p > v else "CE"
    if rule == "B":
        return "PE" if p <= o else "CE"
    if rule == "C":
        return "CE"
    raise ValueError(f"unknown side rule {rule}")


LAST_INDEX_CANDLE = dtime(15, 29)


def previous_session(index_1m: pd.DataFrame, day: pd.Timestamp) -> pd.Timestamp | None:
    """The latest earlier date with a full set of index candles, else None.

    A day whose capture stopped early is not a usable previous session, so its last close is never
    taken as V and its date is never used to look up the India VIX.
    """
    dates = index_1m.index.normalize()
    earlier = dates[dates < pd.Timestamp(day).normalize()]
    if earlier.empty:
        return None
    prev = earlier.max()
    if index_1m[dates == prev].index[-1].time() < LAST_INDEX_CANDLE:
        return None
    return pd.Timestamp(prev)


def session_facts(
    index_1m: pd.DataFrame, day: pd.Timestamp, entry_ts: pd.Timestamp
) -> tuple[float, float, float] | str:
    """(P, O, V) for the day, or the reason one of them is missing."""
    day = pd.Timestamp(day).normalize()
    dates = index_1m.index.normalize()
    today = index_1m[dates == day]
    if today.empty:
        return "no index candles"
    first = today.index[0]
    if first != day + pd.Timedelta(hours=9, minutes=15):
        return "no 09:15 candle"
    last_ts = entry_ts - STEP
    if last_ts not in today.index:
        return "no 10:14 candle"
    prev = previous_session(index_1m, day)
    if prev is None:
        return "no previous close"
    return (
        float(today.loc[last_ts, "close"]),
        float(today["open"].iloc[0]),
        float(index_1m[dates == prev]["close"].iloc[-1]),
    )


def _spot_at(index_1m: pd.DataFrame, ts: pd.Timestamp) -> float | None:
    pos = index_1m.index.searchsorted(ts, side="right") - 1
    if pos < 0 or index_1m.index[pos].date() != ts.date():
        return None
    return float(index_1m["close"].iloc[pos])


def _marks(
    pair: pd.DataFrame, ts0: pd.Timestamp, exit_ts: pd.Timestamp
) -> dict[pd.Timestamp, tuple[float, float]]:
    """For each session the position was held through: the spread value at its last candle, and
    the worst (highest) spread value reached in it."""
    held = pair.loc[ts0:exit_ts]
    out: dict[pd.Timestamp, tuple[float, float]] = {}
    for day, rows in held.groupby(held.index.normalize()):
        out[pd.Timestamp(day)] = (
            float(rows["s_close"].iloc[-1] - rows["l_close"].iloc[-1]),
            float((rows["s_high"] - rows["l_low"]).max()),
        )
    return out


@dataclass
class ShadowResult:
    rule: str
    trades: list[dict[str, Any]] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)
    open_positions: list[dict[str, Any]] = field(default_factory=list)


def simulate_rule(
    rule: str,
    bars: OptionBars,
    index_1m: pd.DataFrame,
    vix_daily: pd.Series,
    rules: Rules = REGISTERED,
    model: lab.Model | None = None,
) -> ShadowResult:
    """Replay one side rule over every stored session, oldest first."""
    model = model or lab.CONSERVATIVE
    result = ShadowResult(rule)
    free_at = pd.Timestamp.min
    entry_clock, reverse_clock = (
        intraday._clock(rules.entry_time),
        intraday._clock(rules.reverse_until),
    )
    vix = vix_daily.copy()
    vix.index = pd.DatetimeIndex(vix.index).normalize()
    episode = 0
    for day in bars.days():
        ts = day + pd.Timedelta(hours=entry_clock.hour, minutes=entry_clock.minute)
        if free_at > ts:
            if free_at == pd.Timestamp.max:
                result.skipped["a position is still open"] += 1
            continue
        facts = session_facts(index_1m, day, ts)
        if isinstance(facts, str):
            result.skipped[facts] += 1
            continue
        p, o, v = facts
        expiry = intraday._nearest_expiry(bars, day, rules.max_dte)
        if expiry is None:
            result.skipped["no expiry"] += 1
            continue
        if rules.vix_ceiling is not None:
            level = vix.get(previous_session(index_1m, day))
            if level is None or pd.isna(level):
                result.skipped["no vix"] += 1
                continue
            if float(level) >= rules.vix_ceiling:
                result.skipped["vix ceiling"] += 1
                continue
        if rules.gap_floor is not None and p / v - 1 <= rules.gap_floor:
            result.skipped["gap down"] += 1
            continue
        side, spot, reversals = choose_side(rule, p, o, v), p, 0
        episode += 1
        while True:
            opened = intraday._open_spread(bars, expiry, side, ts, spot, rules.width)
            if opened is None:
                result.skipped["no prices"] += 1
                break
            sold, long_, pair, entry = opened
            walk = intraday.walk_position(pair, ts, entry[0] - entry[1], expiry, rules)
            if (
                walk is not None
                and walk.reason == "expiry"
                and walk.exit_ts.time() < LAST_INDEX_CANDLE
            ):
                walk = None  # the expiry day is only partly stored: the position is still open
            if walk is None:
                held = pair.loc[ts:]
                result.open_positions.append(
                    {
                        "rule": rule,
                        "episode": episode,
                        "entry": ts,
                        "side": side,
                        "sold": sold,
                        "long": long_,
                        "credit": entry[0] - entry[1],
                        "lot": intraday.lot_size_for(ts),
                        "marks": _marks(pair, ts, held.index[-1]),
                    }
                )
                free_at = pd.Timestamp.max
                break
            record = intraday._trade_record(ts, side, expiry, sold, long_, entry, walk, model)
            record.update(
                rule=rule,
                episode=episode,
                reversal=reversals,
                lot=intraday.lot_size_for(ts),
                marks=_marks(pair, ts, walk.exit_ts),
            )
            result.trades.append(record)
            free_at = walk.exit_ts
            reverses = (
                walk.reason == "stop"
                and rules.reverse
                and walk.exit_ts.normalize() == day
                and reversals < rules.max_reversals
                and walk.exit_ts.time() <= reverse_clock
            )
            if not reverses:
                break
            spot_now = _spot_at(index_1m, walk.exit_ts)
            if spot_now is None:
                break
            reversals += 1
            ts, spot, side = walk.exit_ts + STEP, spot_now, ("CE" if side == "PE" else "PE")
    return result


def equity_paths(result: ShadowResult, days: list[pd.Timestamp]) -> pd.DataFrame:
    """Marked-to-market equity per session in rupees, from zero: ``eod`` at each session's last
    candle and ``low`` at the worst point reached inside it.

    Closed trades count at their net result. A position still held counts as its credit less the
    spread value, times its lot, with no cost until it closes; a session with no stored candle for
    it carries the last known value forward.
    """
    days = sorted(pd.Timestamp(d).normalize() for d in days)
    eod, low = [], []
    for day in days:
        realised = sum(t["net"] for t in result.trades if t["exit"].normalize() <= day)
        end, worst = realised, realised
        for item in [*result.trades, *result.open_positions]:
            closed_on = item["exit"].normalize() if "exit" in item else None
            if item["entry"].normalize() <= day and (closed_on is None or day < closed_on):
                known = [d for d in item["marks"] if d <= day]
                if not known:
                    continue
                if day in item["marks"]:
                    close_val, worst_val = item["marks"][day]
                else:
                    close_val = worst_val = item["marks"][max(known)][0]
                end += (item["credit"] - close_val) * item["lot"]
                worst += (item["credit"] - worst_val) * item["lot"]
        eod.append(end)
        low.append(min(end, worst))
    return pd.DataFrame({"eod": eod, "low": low}, index=pd.DatetimeIndex(days), dtype=float)


def equity_curve(result: ShadowResult, days: list[pd.Timestamp]) -> pd.Series:
    return equity_paths(result, days)["eod"]


def daily_pnl(equity: pd.Series) -> pd.Series:
    return equity.diff().fillna(equity.iloc[0] if len(equity) else 0.0)


def max_drawdown(paths: pd.DataFrame | pd.Series) -> float:
    """Largest fall from the best end-of-session equity to the worst point of a later session."""
    if isinstance(paths, pd.Series):
        paths = pd.DataFrame({"eod": paths, "low": paths})
    if paths.empty:
        return 0.0
    peak = np.maximum.accumulate(np.r_[0.0, paths["eod"].to_numpy()])[:-1]
    return float((peak - paths["low"].to_numpy()).max())


def worst_day(paths: pd.DataFrame) -> float:
    """Biggest one-session fall from the previous close, using the worst point inside the session."""
    if paths.empty:
        return 0.0
    before = np.r_[0.0, paths["eod"].to_numpy()[:-1]]
    return float((paths["low"].to_numpy() - before).min())


def block_bootstrap_lower(series: np.ndarray, level: float = BOOTSTRAP_LEVEL) -> float:
    """Lower bound of the mean from a moving-block bootstrap with the registered block and seed."""
    n = len(series)
    if n == 0:
        return float("nan")
    block = min(BOOTSTRAP_BLOCK, n)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    starts = rng.integers(0, n - block + 1, size=(BOOTSTRAP_DRAWS, -(-n // block)))
    offsets = np.arange(block)
    means = np.empty(BOOTSTRAP_DRAWS)
    for i in range(BOOTSTRAP_DRAWS):
        picked = series[(starts[i][:, None] + offsets).ravel()[:n]]
        means[i] = picked.mean()
    return float(np.quantile(means, level))


def episodes_closed(result: ShadowResult) -> int:
    open_ids = {p["episode"] for p in result.open_positions}
    return len({t["episode"] for t in result.trades} - open_ids)


def evaluate(results: dict[str, ShadowResult], days: list[pd.Timestamp]) -> dict[str, Any]:
    """The registered gates for each candidate, plus whether the registered end has been reached.

    No-trade days count as zero in the daily series. Nothing here is a verdict before the end:
    ``final`` is False until 252 sessions are stored, and the gates are then only a progress read.
    """
    sessions = len({pd.Timestamp(d).normalize() for d in days})
    control = daily_pnl(equity_curve(results[CONTROL], days)) if CONTROL in results else None
    final = sessions >= REGISTERED_SESSIONS
    out: dict[str, Any] = {
        "version": VERSION,
        "sessions": sessions,
        "final": final,
    }
    for name in CANDIDATES:
        if name not in results:
            continue
        res = results[name]
        paths = equity_paths(res, days)
        daily = daily_pnl(paths["eod"])
        net = float(sum(t["net"] for t in res.trades))
        stress = net - float(sum(t["cost"] for t in res.trades))
        episodes = episodes_closed(res)
        gates = {
            "episodes": episodes >= MIN_EPISODES,
            "net": net >= MIN_NET,
            "cost_stress": stress > 0,
            "drawdown": max_drawdown(paths) <= MAX_DRAWDOWN,
            "daily_cap": worst_day(paths) >= -DAILY_CAP,
            "mean_bound": block_bootstrap_lower(daily.to_numpy()) > 0,
        }
        gates["beats_control"] = bool(
            control is not None
            and control.index.equals(daily.index)
            and block_bootstrap_lower((daily - control).to_numpy()) > 0
        )
        out[name] = {
            "episodes": episodes,
            "trades": len(res.trades),
            "net": round(net, 2),
            "net_double_cost": round(stress, 2),
            "max_drawdown": round(max_drawdown(paths), 2),
            "worst_day": round(worst_day(paths), 2),
            "gates": gates,
            "all_gates": final and all(gates.values()),
            "verdict": (
                "pass" if final and all(gates.values()) else "fail" if final else "not due yet"
            ),
            "skipped": dict(res.skipped),
            "still_open": len(res.open_positions),
        }
    return out
