"""Intraday replay of an overnight credit spread on 5-minute option bars (research only).

The daily replay in ``lab.py`` cannot see an entry at 10:15, a stop inside the
day or a target, which is where an overnight spread's result is decided. This
module replays those on real 5-minute bars of expired Nifty contracts.

No orders, no broker and no network: it reads bar files already on disk (see
``scripts/algo_backtest/fetch_upstox_expired.py``) and returns trades.

How a trade is replayed:

- The decision at ``entry_time`` uses only bars that closed before it. Spot is
  implied from put-call parity of the at-the-money strikes, so no spot feed is
  needed, and the entry fill is the open of the entry bar.
- The spread is sold at the money and bought ``width`` points away.
- Each bar checks, in this order: the time exit (first bar at or after
  ``exit_time`` on a later session), the stop, the target, expiry. The stop
  uses the pessimistic spread high (sold leg high less long leg low) and fills
  at the trigger plus ``stop_slip_pts``, or at the bar open when it gaps
  through. The target needs the bar's close to be at or under the target.
- A stop before ``reverse_until`` reopens on the opposite side at the next bar.
- A position held overnight blocks the next entry, as in the published table.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import time as dtime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.algos import lab

FIELDS = ["open", "high", "low", "close"]
BAR = pd.Timedelta(minutes=5)
LOT_CHANGE = pd.Timestamp("2025-12-30")  # Nifty lot size 75 until this date, 65 after


def lot_size_for(day: pd.Timestamp) -> int:
    return 65 if pd.Timestamp(day) >= LOT_CHANGE else 75


def _clock(text: str) -> dtime:
    hour, minute = text.split(":")
    return dtime(int(hour), int(minute))


@dataclass(frozen=True)
class Rules:
    width: int = 400
    entry_time: str = "10:15"
    exit_time: str = "15:00"
    stop_pts: float | None = 43.8
    stop_slip_pts: float = 2.0
    target_pts: float | None = 10.0
    reverse: bool = True
    max_reversals: int = 3
    reverse_until: str = "14:30"
    side_rule: str = "vs_prev_close"  # put | call | vs_prev_close | vs_morning | lean | flip | fade
    vix_ceiling: float | None = 20.0
    gap_floor: float | None = -0.01
    max_dte: int = 8


class OptionBars:
    """5-minute bars keyed by (expiry, kind, strike), kept in IST wall-clock time."""

    def __init__(self, frames: dict[tuple[Any, str, float], pd.DataFrame]):
        self._frames: dict[tuple[pd.Timestamp, str, float], pd.DataFrame] = {}
        self._strikes: dict[tuple[pd.Timestamp, str], list[float]] = {}
        for (expiry, kind, strike), frame in frames.items():
            frame = frame.sort_index()
            frame = frame[~frame.index.duplicated(keep="last")]
            if len(frame):
                self._frames[(pd.Timestamp(expiry), kind, float(strike))] = frame
        for expiry, kind, strike in self._frames:
            self._strikes.setdefault((expiry, kind), []).append(strike)
        for strikes in self._strikes.values():
            strikes.sort()
        self._pairs: dict[tuple, pd.DataFrame | None] = {}

    @classmethod
    def load(cls, directory: Path) -> OptionBars:
        """Read ``<expiry>_<CE|PE>_<strike>.csv`` files written by the fetcher."""
        frames = {}
        for path in sorted(Path(directory).glob("*.csv")):
            parts = path.stem.split("_")
            if len(parts) != 3 or parts[1] not in ("CE", "PE"):
                continue
            frame = pd.read_csv(path, parse_dates=["timestamp"]).set_index("timestamp")
            frames[(pd.Timestamp(parts[0]), parts[1], float(parts[2]))] = frame
        return cls(frames)

    def expiries(self) -> list[pd.Timestamp]:
        return sorted({key[0] for key in self._frames})

    def days(self) -> list[pd.Timestamp]:
        found: set[pd.Timestamp] = set()
        for frame in self._frames.values():
            found.update(frame.index.normalize().unique())
        return sorted(found)

    def frame(self, expiry, kind: str, strike: float) -> pd.DataFrame | None:
        return self._frames.get((pd.Timestamp(expiry), kind, float(strike)))

    @staticmethod
    def _asof(frame: pd.DataFrame, ts: pd.Timestamp, field: str = "close") -> float | None:
        """Last print at or before ``ts`` on the same session, else None."""
        pos = frame.index.searchsorted(ts, side="right") - 1
        if pos < 0 or frame.index[pos].date() != ts.date():
            return None
        value = float(frame[field].iloc[pos])
        return value if value > 0 else None

    def spot_at(self, expiry, ts) -> float | None:
        """Nifty implied by put-call parity of the strikes nearest the money at ``ts``."""
        ts, expiry = pd.Timestamp(ts), pd.Timestamp(expiry)
        puts = set(self._strikes.get((expiry, "PE"), []))
        estimates = []
        for strike in self._strikes.get((expiry, "CE"), []):
            if strike not in puts:
                continue
            call = self._asof(self._frames[(expiry, "CE", strike)], ts)
            put = self._asof(self._frames[(expiry, "PE", strike)], ts)
            if call is not None and put is not None:
                estimates.append((abs(call - put), strike + call - put))
        if not estimates:
            return None
        estimates.sort()
        return float(np.median([value for _, value in estimates[:3]]))

    def pair(self, expiry, kind: str, sold: float, long_: float) -> pd.DataFrame | None:
        """Both legs on one timeline. A leg with no trade in a bar carries its last close."""
        key = (pd.Timestamp(expiry), kind, float(sold), float(long_))
        if key in self._pairs:
            return self._pairs[key]
        s, lg = self.frame(expiry, kind, sold), self.frame(expiry, kind, long_)
        out = None
        if s is not None and lg is not None:
            index = s.index.union(lg.index)
            parts = []
            for prefix, frame in (("s_", s), ("l_", lg)):
                f = frame[FIELDS].reindex(index)
                close = f["close"].ffill()
                for col in FIELDS:
                    f[col] = f[col].fillna(close)
                parts.append(f.add_prefix(prefix))
            out = pd.concat(parts, axis=1).dropna()
        self._pairs[key] = out
        return out


def daily_context(nifty: pd.DataFrame, vix: pd.Series) -> pd.DataFrame:
    """Prior close, 20-day average and prior India VIX per session, none of it from the same day."""
    close = nifty["Close"]
    return pd.DataFrame(
        {
            "prev_close": close.shift(1),
            "sma20": close.rolling(20).mean().shift(1),
            "prev_vix": vix.shift(1).reindex(close.index),
        }
    )


@dataclass
class Walk:
    exit_ts: pd.Timestamp
    exit_value: float
    reason: str
    exit_s: float
    exit_l: float


def walk_position(
    pair: pd.DataFrame, ts0: pd.Timestamp, credit: float, expiry: pd.Timestamp, rules: Rules
) -> Walk | None:
    """Follow an open spread bar by bar until something closes it, or None when the data ends first."""
    sub = pair.loc[ts0:]
    if sub.empty:
        return None
    entry_day = ts0.normalize()
    expiry_day = pd.Timestamp(expiry).normalize()
    trigger = credit + rules.stop_pts if rules.stop_pts is not None else None
    exit_clock = _clock(rules.exit_time)
    days = sub.index.normalize()
    last_of_day = np.r_[days[1:] != days[:-1], True]
    for i, row in enumerate(sub.itertuples()):
        ts = sub.index[i]
        day = days[i]
        open_val = row.s_open - row.l_open
        if day > entry_day and ts.time() >= exit_clock:
            return Walk(ts, open_val, "time", row.s_open, row.l_open)
        if trigger is not None:
            if ts > ts0 and open_val >= trigger:
                return Walk(ts, open_val + rules.stop_slip_pts, "stop", row.s_open, row.l_open)
            if row.s_high - row.l_low >= trigger:
                return Walk(ts, trigger + rules.stop_slip_pts, "stop", row.s_close, row.l_close)
        close_val = row.s_close - row.l_close
        if rules.target_pts is not None and ts > ts0 and close_val <= rules.target_pts:
            return Walk(ts, close_val, "target", row.s_close, row.l_close)
        if day == expiry_day and last_of_day[i]:
            return Walk(ts, close_val, "expiry", row.s_close, row.l_close)
    return None


def entry_value(pair: pd.DataFrame, ts: pd.Timestamp) -> tuple[float, float] | None:
    """(sold, long) prices at ``ts``: the bar's open, else the last close earlier the same session."""
    if ts in pair.index:
        row = pair.loc[ts]
        return float(row["s_open"]), float(row["l_open"])
    pos = pair.index.searchsorted(ts, side="right") - 1
    if pos < 0 or pair.index[pos].date() != ts.date():
        return None
    row = pair.iloc[pos]
    return float(row["s_close"]), float(row["l_close"])


@dataclass
class SimResult:
    trades: list[dict[str, Any]]
    skipped: Counter


def _trade_record(
    ts0: pd.Timestamp,
    kind: str,
    expiry: pd.Timestamp,
    sold: float,
    long_: float,
    entry: tuple[float, float],
    walk: Walk,
    model: lab.Model,
) -> dict[str, Any]:
    credit = entry[0] - entry[1]
    pts = credit - walk.exit_value
    cost = lab.trade_cost(model, list(entry), [walk.exit_s, walk.exit_l], [True, False])
    lot = lot_size_for(ts0)
    return {
        "entry": ts0,
        "exit": walk.exit_ts,
        "side": kind,
        "expiry": pd.Timestamp(expiry),
        "sold": sold,
        "long": long_,
        "credit": credit,
        "exit_value": walk.exit_value,
        "reason": walk.reason,
        "pts": pts,
        "cost": cost,
        "net": pts * lot - cost,
    }


def _nearest_expiry(bars: OptionBars, day: pd.Timestamp, max_dte: int) -> pd.Timestamp | None:
    for expiry in bars.expiries():
        if expiry >= day and (expiry - day).days <= max_dte:
            return expiry
    return None


def _choose_side(
    rule: str,
    bars: OptionBars,
    expiry,
    ts: pd.Timestamp,
    spot: float,
    ctx: pd.Series,
    last_side: str | None,
) -> str | None:
    if rule == "put":
        return "PE"
    if rule == "call":
        return "CE"
    if rule in ("vs_prev_close", "fade"):
        if pd.isna(ctx["prev_close"]):
            return None
        up = spot >= ctx["prev_close"]
        return "PE" if up == (rule == "vs_prev_close") else "CE"
    if rule == "vs_morning":
        ref = bars.spot_at(expiry, ts.normalize() + pd.Timedelta(hours=9, minutes=30))
        return None if ref is None else ("PE" if spot >= ref else "CE")
    if rule == "lean":
        return (
            None if pd.isna(ctx["sma20"]) else ("PE" if ctx["prev_close"] < ctx["sma20"] else "CE")
        )
    if rule == "flip":
        return "CE" if last_side in (None, "PE") else "PE"
    raise ValueError(f"unknown side rule {rule}")


def _open_spread(bars: OptionBars, expiry, kind: str, ts: pd.Timestamp, spot: float, width: int):
    sold = float(round(spot / 50) * 50)
    long_ = sold - width if kind == "PE" else sold + width
    pair = bars.pair(expiry, kind, sold, long_)
    if pair is None:
        return None
    entry = entry_value(pair, ts)
    if entry is None or entry[0] - entry[1] <= 0:
        return None
    return sold, long_, pair, entry


def simulate(
    bars: OptionBars,
    context: pd.DataFrame,
    rules: Rules,
    start: str | None = None,
    end: str | None = None,
    model: lab.Model | None = None,
) -> SimResult:
    """Replay the rules session by session over the bars on disk."""
    model = model or lab.CONSERVATIVE
    trades: list[dict[str, Any]] = []
    skipped: Counter = Counter()
    free_at = pd.Timestamp.min
    last_side: str | None = None
    entry_clock, reverse_clock = _clock(rules.entry_time), _clock(rules.reverse_until)
    for day in bars.days():
        if (start and day < pd.Timestamp(start)) or (end and day > pd.Timestamp(end)):
            continue
        if day not in context.index:
            continue
        ts = day + pd.Timedelta(hours=entry_clock.hour, minutes=entry_clock.minute)
        if free_at > ts:
            continue
        ctx = context.loc[day]
        expiry = _nearest_expiry(bars, day, rules.max_dte)
        if expiry is None:
            skipped["no expiry"] += 1
            continue
        spot = bars.spot_at(expiry, ts - BAR)
        if spot is None:
            skipped["no spot"] += 1
            continue
        if rules.vix_ceiling is not None and ctx["prev_vix"] >= rules.vix_ceiling:
            skipped["vix ceiling"] += 1
            continue
        if rules.gap_floor is not None and not pd.isna(ctx["prev_close"]):
            if spot / ctx["prev_close"] - 1 <= rules.gap_floor:
                skipped["gap down"] += 1
                continue
        side = _choose_side(rules.side_rule, bars, expiry, ts, spot, ctx, last_side)
        reversals = 0
        while side is not None:
            opened = _open_spread(bars, expiry, side, ts, spot, rules.width)
            if opened is None:
                skipped["no prices"] += 1
                break
            sold, long_, pair, entry = opened
            walk = walk_position(pair, ts, entry[0] - entry[1], expiry, rules)
            if walk is None:
                skipped["data ended"] += 1
                break
            trades.append(_trade_record(ts, side, expiry, sold, long_, entry, walk, model))
            last_side, free_at = side, walk.exit_ts
            same_day = walk.exit_ts.normalize() == day
            if not (
                walk.reason == "stop"
                and rules.reverse
                and same_day
                and reversals < rules.max_reversals
                and walk.exit_ts.time() <= reverse_clock
            ):
                break
            reversals += 1
            ts = walk.exit_ts + BAR
            spot = bars.spot_at(expiry, walk.exit_ts)
            if spot is None:
                break
            side = "CE" if side == "PE" else "PE"
    return SimResult(trades, skipped)


def replay_published(
    bars: OptionBars, rows: list[dict[str, Any]], rules: Rules, model: lab.Model | None = None
) -> list[dict[str, Any]]:
    """Replay a list of published entries (time, side, strikes, credit) under the exit rules.

    ``rows`` need ``ent`` (timestamp), ``kind``, ``sold``, ``long`` and ``credit``. The expiry is the
    one whose real price at the entry time is closest to the published credit.
    """
    model = model or lab.CONSERVATIVE
    out = []
    for row in rows:
        ts = pd.Timestamp(row["ent"]).floor("5min")
        day = ts.normalize()
        best = None
        for expiry in bars.expiries():
            if expiry < day or (expiry - day).days > rules.max_dte:
                continue
            pair = bars.pair(expiry, row["kind"], row["sold"], row["long"])
            entry = None if pair is None else entry_value(pair, ts)
            if entry is None:
                continue
            gap = abs(entry[0] - entry[1] - row["credit"])
            if best is None or gap < best[0]:
                best = (gap, expiry, pair, entry)
        if best is None:
            continue
        _, expiry, pair, entry = best
        walk = walk_position(pair, ts, entry[0] - entry[1], expiry, rules)
        if walk is None:
            continue
        rec = _trade_record(ts, row["kind"], expiry, row["sold"], row["long"], entry, walk, model)
        rec["published_credit"] = row["credit"]
        out.append(rec)
    return out
