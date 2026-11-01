"""Weekly structures S2 to S4 of docs/algos/structures-registration.md (condor and weekly call spread).

One entry per weekly expiry, on the session a fixed number of sessions before it, held to the last
bar of the expiry session: no stop, no target, no reversal. Reuses the filters, the spread opener
and the marking of the forward shadow replay. Pure functions over bars and frames: no database, no
network, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime

import numpy as np
import pandas as pd

from services.algos import forward_shadow as fs
from services.algos import intraday, lab
from services.algos.intraday import OptionBars

WIDTH = 250
INNER = 150
LAST_BAR = dtime(15, 25)  # the last 5-minute bar of a full session in the expired-contract data


@dataclass(frozen=True)
class WeeklySpec:
    name: str
    kind: str  # "condor" or "call"
    sessions_before: int
    entry_time: str


S2 = WeeklySpec("S2", "condor", 2, "10:15")
S3 = WeeklySpec("S3", "call", 2, "10:15")
S4 = WeeklySpec("S4", "condor", 1, "14:30")
SPECS = {s.name: s for s in (S2, S3, S4)}


def legs_for(spec: WeeklySpec) -> list[tuple[str, int]]:
    """(kind, offset in points of the sold strike from the money) for each spread."""
    if spec.kind == "condor":
        return [("CE", INNER), ("PE", -INNER)]
    return [("CE", 0)]


def _enter(spec, bars, index_1m, vix, day, expiry, width, require_entry_candle):
    """Open the structure on ``day`` for ``expiry``: (entry time, opened legs) or the reason not."""
    hour, minute = (int(x) for x in spec.entry_time.split(":"))
    ts = day + pd.Timedelta(hours=hour, minutes=minute)
    facts = fs.session_facts(index_1m, day, ts)
    if isinstance(facts, str):
        return facts
    p, _o, v = facts
    level = vix.get(fs.previous_session(index_1m, day))
    if level is None or pd.isna(level):
        return "no vix"
    if float(level) >= fs.REGISTERED.vix_ceiling:
        return "vix ceiling"
    if p / v - 1 <= fs.REGISTERED.gap_floor:
        return "gap down"
    opened = []
    for kind, offset in legs_for(spec):
        one = intraday._open_spread(bars, expiry, kind, ts, p + offset, width)
        if one is None:
            return "no prices"
        opened.append((kind, *one))
    if require_entry_candle and not all(
        ts in bars.frame(expiry, kind, strike).index
        for kind, sold, long_, _pair, _entry in opened
        for strike in (sold, long_)
    ):
        return "no candle at the entry minute"
    return ts, opened


def _skip(result: fs.ShadowResult, expiry: pd.Timestamp, reason: str) -> None:
    result.skipped[reason] += 1
    result.weeks_skipped.append({"expiry": expiry, "reason": reason})


def _open_record(spec, n, ts, e, opened, lot, last_stored):
    """A week entered whose expiry session is not stored yet, marked up to the last stored candle."""
    legs, credit, marks = [], 0.0, {}
    for kind, sold, long_, pair, entry in opened:
        legs.append({"kind": kind, "sold": sold, "long": long_,
                     "entry_s": float(entry[0]), "entry_l": float(entry[1])})  # fmt: skip
        credit += entry[0] - entry[1]
        for d, (close_val, worst) in fs._marks(pair, ts, last_stored).items():
            a, b = marks.get(d, (0.0, 0.0))
            marks[d] = (a + close_val, b + worst)
    return {"rule": spec.name, "episode": n, "entry": ts, "expiry": e, "side": spec.kind,
            "credit": credit, "lot": lot, "legs": legs, "marks": marks}  # fmt: skip


def simulate_weekly(
    spec: WeeklySpec,
    bars: OptionBars,
    index_1m: pd.DataFrame,
    vix_daily: pd.Series,
    allowed_days: set[pd.Timestamp],
    model: lab.Model | None = None,
    width: int = WIDTH,
    last_bar: dtime = LAST_BAR,
    require_entry_candle: bool = False,
    first_expiry: pd.Timestamp | None = None,
) -> fs.ShadowResult:
    """Replay one weekly structure over every stored expiry whose entry session is in ``allowed_days``.

    ``last_bar`` is the time of the last candle of a full expiry session (15:25 for five-minute
    bars, 15:29 for one-minute bars). ``require_entry_candle`` refuses a week in which either leg has
    no candle at the entry minute, instead of using the last earlier close. ``first_expiry`` leaves
    out every earlier expiry. A week entered whose expiry session is not stored yet is returned in
    ``open_positions`` (marked to the last stored candle), never as a skipped week.
    """
    model = model or lab.CONSERVATIVE
    result = fs.ShadowResult(spec.name)
    days = bars.days()
    position = {d: i for i, d in enumerate(days)}
    allowed = {pd.Timestamp(d).normalize() for d in allowed_days}
    vix = vix_daily.copy()
    vix.index = pd.DatetimeIndex(vix.index).normalize()
    for n, expiry in enumerate(bars.expiries(), start=1):
        e = pd.Timestamp(expiry).normalize()
        if first_expiry is not None and e < pd.Timestamp(first_expiry).normalize():
            continue
        ahead = bool(days) and e > days[-1]
        if ahead:
            # Expiry session not stored yet: the entry session is taken as that many weekdays before.
            day = pd.Timestamp(np.busday_offset(e.date(), -spec.sessions_before, roll="backward"))
            if day not in position:
                continue  # the entry session is not stored (yet): nothing has been entered
        elif e not in position or position[e] - spec.sessions_before < 0:
            _skip(result, e, "expiry is not a stored session")
            continue
        else:
            day = days[position[e] - spec.sessions_before]
        if day not in allowed:
            continue
        entered = _enter(spec, bars, index_1m, vix, day, expiry, width, require_entry_candle)
        if isinstance(entered, str):
            _skip(result, e, entered)
            continue
        ts, opened = entered
        lot = intraday.lot_size_for(ts)
        if ahead:
            result.open_positions.append(
                _open_record(spec, n, ts, e, opened, lot, days[-1] + pd.Timedelta(days=1))
            )
            continue
        exits, last_ts = [], None
        for _kind, _sold, _long, pair, _entry in opened:
            rows = pair[pair.index.normalize() == e]
            if rows.empty or rows.index[-1].time() < last_bar:
                exits = []
                break
            last = rows.iloc[-1]
            exits.append((float(last["s_close"]), float(last["l_close"])))
            last_ts = rows.index[-1] if last_ts is None else min(last_ts, rows.index[-1])
        if not exits:
            _skip(result, e, "expiry day only partly stored")
            continue
        legs, credit, exit_value, cost = [], 0.0, 0.0, 0.0
        marks: dict[pd.Timestamp, tuple[float, float]] = {}
        for (kind, sold, long_, pair, entry), (x_s, x_l) in zip(opened, exits, strict=True):
            legs.append(
                {"kind": kind, "sold": sold, "long": long_, "entry_s": float(entry[0]),
                 "entry_l": float(entry[1]), "exit_s": x_s, "exit_l": x_l}
            )  # fmt: skip
            credit += entry[0] - entry[1]
            exit_value += x_s - x_l
            cost += lab.trade_cost(model, [entry[0], entry[1]], [x_s, x_l], [True, False])
            for d, (close_val, worst) in fs._marks(pair, ts, last_ts).items():
                a, b = marks.get(d, (0.0, 0.0))
                marks[d] = (a + close_val, b + worst)
        pts = credit - exit_value
        result.trades.append(
            {
                "rule": spec.name, "episode": n, "entry": ts, "exit": last_ts, "expiry": e,
                "side": spec.kind, "credit": credit, "exit_value": exit_value, "reason": "expiry",
                "pts": pts, "cost": cost, "net": pts * lot - cost, "lot": lot, "legs": legs,
                "marks": marks,
            }
        )  # fmt: skip
    return result
