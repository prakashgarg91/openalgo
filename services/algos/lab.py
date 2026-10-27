"""The Lab: replay an algo over real history, with no broker.

It runs the same ``score_regime`` and ``build`` the live runner uses over daily
Nifty, India VIX and global history, prices the legs with a model, and reports
what the algo would have done. The model is a stand-in for option prices that
history does not provide, so every result carries its caveats.

Two pricing models are offered. ``standard`` is the simple one (flat volatility,
flat costs) and flatters a premium seller. ``conservative`` adds volatility skew,
volatility that follows the day's VIX move, and costs that scale with how thin
the far strikes are. Judge an algo on the conservative one.

Only :func:`load_history` does I/O (HTTP, then a small file cache). Everything
else is a pure function of the history it is given.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from services.algos.context import MarketInputs, RegimeResult, score_regime
from services.algos.pricing import bs, expiry_after, num
from services.algos.templates import ALGOS, build
from utils.logging import get_logger

logger = get_logger(__name__)

SERIES = {
    "nifty": "^NSEI",
    "vix": "^INDIAVIX",
    "spx": "^GSPC",
    "ndx": "^IXIC",
    "crude": "CL=F",
    "dxy": "DX-Y.NYB",
}
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
FETCH_TIMEOUT = 12.0
FETCH_ATTEMPTS = 3
CACHE_MAX_AGE_HOURS = 20
HISTORY_RANGE = "10y"
WARMUP_DAYS = 25
MORNING_HOLD_YEARS = 0.25 / 365  # about 09:25 to 15:25
LOT_SIZE = 75
CAPITAL = 500_000
MIN_TRADES_FOR_STATS = 1


class HistoryUnavailable(Exception):
    """Market history could not be loaded. The message is written for a trader."""


@dataclass(frozen=True)
class Model:
    """How option prices and costs are approximated."""

    name: str
    label: str
    #: Relative IV change per 50-point step out of the money, puts and calls.
    skew_put_per_step: float = 0.0
    skew_call_per_step: float = 0.0
    #: Share of the day's VIX change applied to volatility at the exit mark.
    vol_follows_day: float = 0.0
    #: Flat rupees per lot per trade. None means use the itemised costs below.
    flat_cost: float | None = 300.0
    spread_floor_pts: float = 0.5
    spread_pct: float = 0.03
    brokerage: float = 80.0
    stt_pct: float = 0.001
    exchange_pct: float = 0.000345


STANDARD = Model("standard", "Standard (flat volatility, flat costs)")
CONSERVATIVE = Model(
    "conservative",
    "Conservative (skew, volatility moves, costs that grow on far strikes)",
    skew_put_per_step=0.015,
    skew_call_per_step=-0.01,
    vol_follows_day=0.5,
    flat_cost=None,
)
MODELS = {m.name: m for m in (STANDARD, CONSERVATIVE)}


@dataclass
class History:
    """Daily frames with Open and Close columns, indexed by naive date."""

    frames: dict[str, pd.DataFrame]
    notes: list[str] = field(default_factory=list)


@dataclass
class LabResult:
    algo_id: str
    model: str
    start: str
    end: str
    days: int
    trades: list[dict[str, Any]]
    metrics: dict[str, Any]
    yearly: dict[int, dict[str, Any]]
    curve: list[list[Any]]
    skipped: dict[str, int]
    notes: list[str]


# ---------------------------------------------------------------------------
# History: the only I/O in this module
# ---------------------------------------------------------------------------


def parse_chart(payload: dict[str, Any]) -> pd.DataFrame:
    """Open and Close by date from a Yahoo chart response."""
    try:
        result = payload["chart"]["result"][0]
        offset = int(result["meta"].get("gmtoffset") or 0)
        quote = result["indicators"]["quote"][0]
        index = pd.to_datetime([int(t) + offset for t in result["timestamp"]], unit="s")
        frame = pd.DataFrame(
            {"Open": quote["open"], "Close": quote["close"]}, index=index.normalize()
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise HistoryUnavailable("The market data provider sent an unreadable reply.") from exc
    frame = frame.dropna(subset=["Close"])
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    if frame.empty:
        raise HistoryUnavailable("The market data provider sent no history.")
    return frame


def _fetch_series(symbol: str) -> pd.DataFrame:
    from utils.httpx_client import get_httpx_client

    client = get_httpx_client()
    last: Exception | None = None
    for attempt in range(FETCH_ATTEMPTS):
        try:
            response = client.get(
                YAHOO_URL.format(symbol=symbol),
                params={"range": HISTORY_RANGE, "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=FETCH_TIMEOUT,
            )
            if response.status_code == 200:
                return parse_chart(response.json())
            last = HistoryUnavailable(f"status {response.status_code}")
        except HistoryUnavailable as exc:
            last = exc
        except Exception as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    logger.warning("Could not download history for %s: %s", symbol, last)
    raise HistoryUnavailable(
        "Could not download market history. Check your internet connection and try again "
        "in a minute."
    )


def default_cache_dir() -> Path:
    return Path(os.getenv("ALGO_LAB_CACHE_DIR", "db/algo_lab"))


def _read_cache(path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception:
        return None


def load_history(
    cache_dir: Path | None = None,
    *,
    fetch: Callable[[str], pd.DataFrame] = _fetch_series,
    max_age_hours: float = CACHE_MAX_AGE_HOURS,
    now: Callable[[], float] = time.time,
) -> History:
    """Daily history for every series, from a fresh cache or the provider.

    A series is downloaded only when its cache file is older than
    ``max_age_hours``. If the download fails but an older copy exists, the older
    copy is used and the result says so. With neither, :class:`HistoryUnavailable`
    carries a message a trader can act on.
    """
    cache_dir = Path(cache_dir or default_cache_dir())
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    notes: list[str] = []
    for name, symbol in SERIES.items():
        path = cache_dir / f"{name}.csv"
        cached = _read_cache(path) if path.exists() else None
        fresh = cached is not None and (now() - path.stat().st_mtime) < max_age_hours * 3600
        if fresh:
            frames[name] = cached
            continue
        try:
            frame = fetch(symbol)
        except HistoryUnavailable:
            if cached is None:
                raise
            frames[name] = cached
            notes.append(f"Using saved {name} history because a fresh download failed.")
            continue
        tmp = path.with_suffix(".tmp")
        frame.to_csv(tmp)
        os.replace(tmp, path)
        frames[name] = frame
    return History(frames=frames, notes=notes)


# ---------------------------------------------------------------------------
# Pure replay
# ---------------------------------------------------------------------------


def summarize(pnls: list[float]) -> dict[str, Any]:
    """Win rate, profit factor, drawdown and totals for per-lot results."""
    if len(pnls) < MIN_TRADES_FOR_STATS:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg": 0.0,
            "total": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": None,
            "worst": 0.0,
            "best": 0.0,
        }
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    peak, drawdown, running = 0.0, 0.0, 0.0
    for p in pnls:
        running += p
        peak = max(peak, running)
        drawdown = min(drawdown, running - peak)
    return {
        "trades": len(pnls),
        "win_rate": round(100 * sum(1 for p in pnls if p > 0) / len(pnls), 1),
        "avg": round(sum(pnls) / len(pnls), 1),
        "total": round(sum(pnls), 1),
        "max_drawdown": round(drawdown, 1),
        "profit_factor": round(wins / losses, 2) if losses else None,
        "worst": round(min(pnls), 1),
        "best": round(max(pnls), 1),
    }


def trade_cost(model: Model, entry: list[float], exit_: list[float], sells: list[bool]) -> float:
    """Rupees per lot for one round trip.

    ``entry`` and ``exit_`` are each leg's premium at entry and exit, and
    ``sells[i]`` is True for a short leg. The flat model ignores the legs.
    """
    if model.flat_cost is not None:
        return model.flat_cost
    slip_pts = sum(
        max(model.spread_floor_pts, model.spread_pct * e)
        + max(model.spread_floor_pts, model.spread_pct * x)
        for e, x in zip(entry, exit_, strict=True)
    )
    sell_value = sum(e if short else x for e, x, short in zip(entry, exit_, sells, strict=True))
    turnover = sum(entry) + sum(exit_)
    return (
        slip_pts * LOT_SIZE
        + model.brokerage
        + sell_value * LOT_SIZE * model.stt_pct
        + turnover * LOT_SIZE * model.exchange_pct
    )


def _leg_vol(model: Model, sigma: float, kind: str, steps: int) -> float:
    skew = model.skew_put_per_step if kind == "PE" else model.skew_call_per_step
    return max(0.01, sigma * (1 + skew * steps))


def _price_trade(
    model: Model,
    legs: list[dict[str, Any]],
    *,
    S0: float,
    S1: float,
    T0: float,
    T1: float,
    sig0: float,
    sig1: float,
) -> float:
    """Rupees per lot made by the legs between entry and exit marks."""
    atm = round(S0 / 50) * 50
    entry, exit_, sells, pts = [], [], [], 0.0
    for leg in legs:
        steps = int(str(leg["atm_offset"]).replace("OTM", "") or 0)
        kind = leg["option_type"]
        strike = atm + 50 * steps if kind == "CE" else atm - 50 * steps
        e = bs(S0, strike, T0, _leg_vol(model, sig0, kind, steps), kind)
        x = bs(S1, strike, T1, _leg_vol(model, sig1, kind, steps), kind)
        short = leg["position"] == "S"
        pts += (e - x) if short else (x - e)
        entry.append(e)
        exit_.append(x)
        sells.append(short)
    return pts * LOT_SIZE - trade_cost(model, entry, exit_, sells)


def run_lab(
    history: History,
    algo_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
    model: str = "conservative",
    gated: bool = True,
    capital: float = CAPITAL,
    lot_size: int = LOT_SIZE,
    overrides: dict[str, Any] | None = None,
) -> LabResult:
    """Replay one algo over the history. Raises ``KeyError`` for an unknown algo or model."""
    spec = ALGOS[algo_id]
    pricing = MODELS[model]
    frames = history.frames
    nifty = frames["nifty"]
    nifty = nifty[nifty["Close"] > 0].dropna(subset=["Open", "Close"])
    dates = nifty.index
    opn, cls = nifty["Open"], nifty["Close"]
    vix = frames["vix"]
    vclose = vix["Close"].reindex(dates, method="ffill")
    vopen = vix["Open"].reindex(dates, method="ffill")

    def us_ret(name: str) -> pd.Series:
        r = frames[name]["Close"].pct_change() * 100
        return r.reindex(dates - pd.Timedelta(days=1), method="ffill").set_axis(dates)

    sp, nd, cr, dx = (us_ret(n) for n in ("spx", "ndx", "crude", "dxy"))
    ma20 = cls.rolling(20).mean()
    t_start = pd.Timestamp(start) if start else dates[WARMUP_DAYS]
    t_end = pd.Timestamp(end) if end else dates[-1]

    trades: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    last = len(dates) - (1 if spec.overnight else 0)
    days = 0
    for i in range(WARMUP_DAYS, last):
        t = dates[i]
        if t < t_start or t > t_end:
            continue
        days += 1
        if spec.overnight:
            gap = (float(cls.iloc[i]) / float(cls.iloc[i - 1]) - 1) * 100
            vix_now = num(vclose.iloc[i])
            vix_chg = (vix_now / float(vclose.iloc[i - 1]) - 1) * 100 if vix_now else None
            trend = (float(cls.iloc[i]) / float(ma20.iloc[i]) - 1) * 100
            open_gap = None
        else:
            gap = (float(opn.iloc[i]) / float(cls.iloc[i - 1]) - 1) * 100
            open_gap = gap
            vix_now = num(vopen.iloc[i])
            prev_v = float(vclose.iloc[i - 1])
            vix_chg = (vix_now / prev_v - 1) * 100 if vix_now else None
            trend = (float(cls.iloc[i - 1]) / float(ma20.iloc[i - 1]) - 1) * 100
        inputs = MarketInputs(
            gap_pct=gap,
            sp500_pct=num(sp.iloc[i]),
            nasdaq_pct=num(nd.iloc[i]),
            crude_pct=num(cr.iloc[i]),
            dxy_pct=num(dx.iloc[i]),
            vix=vix_now,
            vix_change_pct=vix_chg,
            nifty_vs_ma20_pct=num(trend),
            open_gap_pct=open_gap,
        )
        regime = score_regime(inputs)
        if not gated:
            # Trade every day, as if the market always suited the algo, to show what
            # the regime gate is worth.
            regime = RegimeResult(spec.allowed_labels[0], regime.bias, regime.score, 1.0, (), ())
        expiry = expiry_after(t)
        dte = (expiry - t).days
        plan = build(
            algo_id,
            regime,
            capital=capital,
            lot_size=lot_size,
            days_to_expiry=dte,
            inputs=inputs,
            **(overrides or {}),
        )
        if plan.action != "trade":
            key = plan.reason.split(".")[0][:70]
            skipped[key] = skipped.get(key, 0) + 1
            continue

        if spec.overnight:
            t1 = dates[i + 1]
            use_expiry = expiry if dte > 1 else expiry + timedelta(days=7)
            S0, S1 = float(cls.iloc[i]), float(opn.iloc[i + 1])
            T0, T1 = (use_expiry - t).days / 365, (use_expiry - t1).days / 365
            sig0 = float(vclose.iloc[i]) / 100
            v_open = num(vopen.iloc[i + 1])
            sig1 = (v_open if v_open and v_open > 0 else float(vclose.iloc[i])) / 100
            if pricing.vol_follows_day:
                move = float(vclose.iloc[i + 1]) / float(vclose.iloc[i]) - 1
                sig1 = sig0 * (1 + pricing.vol_follows_day * move)
        else:
            S0, S1 = float(opn.iloc[i]), float(cls.iloc[i])
            T0 = (expiry - t).days / 365
            T1 = T0 - MORNING_HOLD_YEARS
            v0 = num(vopen.iloc[i])
            sig0 = (v0 if v0 and v0 > 0 else float(vclose.iloc[i - 1])) / 100
            sig1 = float(vclose.iloc[i]) / 100
        pnl = _price_trade(
            pricing, plan.config["legs"], S0=S0, S1=S1, T0=T0, T1=T1, sig0=sig0, sig1=sig1
        )
        trades.append(
            {
                "date": t.strftime("%Y-%m-%d"),
                "regime": regime.label,
                "side": plan.side,
                "pnl": round(pnl, 1),
            }
        )

    pnls = [tr["pnl"] for tr in trades]
    yearly: dict[int, dict[str, Any]] = {}
    for year in sorted({int(tr["date"][:4]) for tr in trades}):
        yearly[year] = summarize([tr["pnl"] for tr in trades if int(tr["date"][:4]) == year])
    running, curve = 0.0, []
    for tr in trades:
        running += tr["pnl"]
        curve.append([tr["date"], round(running, 1)])
    return LabResult(
        algo_id=algo_id,
        model=model,
        start=t_start.strftime("%Y-%m-%d"),
        end=t_end.strftime("%Y-%m-%d"),
        days=days,
        trades=trades,
        metrics=summarize(pnls),
        yearly=yearly,
        curve=curve,
        skipped=dict(sorted(skipped.items(), key=lambda kv: -kv[1])),
        notes=list(history.notes),
    )


__all__ = [
    "CONSERVATIVE",
    "MODELS",
    "STANDARD",
    "History",
    "HistoryUnavailable",
    "LabResult",
    "Model",
    "load_history",
    "parse_chart",
    "run_lab",
    "summarize",
    "trade_cost",
]
