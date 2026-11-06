"""Read-only parser for exported Stratzy Zen credit spread trade records.

Pure module: no network, no clock, no logging. The only file access is
``load_trades``, which reads the JSON file it is given.

Each published record carries two ``trades`` legs: one SELL (the sold short
strike) and one BUY (the long protective strike). Prices are per point; the
record's own ``pnl`` is taken as published in rupees.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))

_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
# Weekly codes: 1-9 for January-September, O/N/D for October-December.
_WEEKLY_MONTH_CODES = {
    **{str(i): i for i in range(1, 10)},
    "O": 10,
    "N": 11,
    "D": 12,
}

# NIFTY26SEP23000PE: base, yy, three-letter month, strike, CE/PE. No day,
# so the expiry day cannot be read from the symbol.
_MONTHLY_RE = re.compile(
    r"^(?P<base>[A-Z]+)(?P<yy>\d{2})(?P<mon>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
    r"(?P<strike>\d+(?:\.\d+)?)(?P<kind>CE|PE)$"
)
# NIFTY2692223450PE: base, yy, weekly month code, dd, strike, CE/PE.
_WEEKLY_RE = re.compile(
    r"^(?P<base>[A-Z]+)(?P<yy>\d{2})(?P<mcode>[1-9ODN])(?P<dd>\d{2})"
    r"(?P<strike>\d+(?:\.\d+)?)(?P<kind>CE|PE)$"
)


@dataclass(frozen=True)
class ZenTrade:
    advice_id: str
    entry_time: datetime  # India time, UTC+5:30
    exit_time: datetime | None
    kind: str  # "PE" (put credit spread) or "CE" (call credit spread)
    sold_symbol: str
    long_symbol: str
    sold_strike: float
    long_strike: float
    width: float  # abs(sold_strike - long_strike)
    expiry: date | None  # None for monthly symbols, which carry no day
    lots: int
    lot_size: int
    entry_credit: float  # points: sold entry minus long entry
    exit_debit: float | None  # points: sold exit minus long exit
    pnl: float  # rupees as published
    margin: float | None
    exit_class: str  # "target" | "stop" | "time" | "unknown"
    # Leg prices in points, kept so costs can be worked out leg by leg. None when the record lacks them.
    sold_entry: float | None = None
    long_entry: float | None = None
    sold_exit: float | None = None
    long_exit: float | None = None


@dataclass(frozen=True)
class ParsedSymbol:
    base: str
    expiry_code: str  # the text between base and strike, used to match legs
    expiry: date | None
    strike: float
    kind: str


def parse_symbol(symbol: object) -> ParsedSymbol | None:
    """Parse NIFTY26SEP23000PE (monthly) or NIFTY2692223450PE (weekly)."""
    if not isinstance(symbol, str):
        return None
    text = symbol.strip().upper()
    match = _MONTHLY_RE.match(text)
    if match:
        expiry_code = match.group("yy") + match.group("mon")
        return ParsedSymbol(
            base=match.group("base"),
            expiry_code=expiry_code,
            expiry=None,
            strike=float(match.group("strike")),
            kind=match.group("kind"),
        )
    match = _WEEKLY_RE.match(text)
    if match:
        code = match.group("mcode")
        month = _WEEKLY_MONTH_CODES[code]
        year = 2000 + int(match.group("yy"))
        day = int(match.group("dd"))
        try:
            expiry = date(year, month, day)
        except ValueError:
            return None
        return ParsedSymbol(
            base=match.group("base"),
            expiry_code=match.group("yy") + code + match.group("dd"),
            expiry=expiry,
            strike=float(match.group("strike")),
            kind=match.group("kind"),
        )
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _parse_utc(text: object) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(IST)


def _exit_class(record: dict) -> str:
    """Classify from summary titles only. Unknown when no label matches."""
    found: set[str] = set()
    for item in record.get("summary") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").lower()
        if re.search(r"\bstop\b|\bsl\b|stoploss|stop loss", title):
            found.add("stop")
        elif re.search(r"\btarget\b|\btp\b", title):
            found.add("target")
        elif re.search(r"\btime\b|square|\beod\b|expiry", title):
            found.add("time")
    return found.pop() if len(found) == 1 else "unknown"


def _leg_exit_price(leg: dict) -> float | None:
    for key in ("avgExitPrice", "exitPrice", "finalExitPrice"):
        value = _number(leg.get(key))
        if value is not None:
            return value
    return None


def _build(record: object) -> tuple[ZenTrade | None, str]:
    """Return (trade, "") when accepted, or (None, reason) when rejected."""
    if not isinstance(record, dict):
        return None, "record is not an object"
    if record.get("executionState") != "EXECUTED":
        return None, "not executed"
    legs = record.get("trades")
    if not isinstance(legs, list) or len(legs) != 2:
        return None, "not a two-leg spread"
    if not all(isinstance(leg, dict) for leg in legs):
        return None, "malformed leg"
    sold_legs = [leg for leg in legs if leg.get("transactionType") == "SELL"]
    buy_legs = [leg for leg in legs if leg.get("transactionType") == "BUY"]
    if len(sold_legs) != 1 or len(buy_legs) != 1:
        return None, "legs are not one SELL and one BUY"
    sold_leg, long_leg = sold_legs[0], buy_legs[0]

    sold = parse_symbol(sold_leg.get("symbol"))
    long = parse_symbol(long_leg.get("symbol"))
    if sold is None or long is None:
        return None, "unrecognised option symbol"
    if sold.kind != long.kind or sold.base != long.base:
        return None, "legs differ in kind or underlying"
    if sold.expiry_code != long.expiry_code:
        return None, "legs differ in expiry"
    if sold.strike == long.strike:
        return None, "zero width spread"
    if sold.kind == "PE" and sold.strike < long.strike:
        return None, "put spread sold below long strike (debit)"
    if sold.kind == "CE" and sold.strike > long.strike:
        return None, "call spread sold above long strike (debit)"

    sold_entry = _number(sold_leg.get("entryPrice"))
    long_entry = _number(long_leg.get("entryPrice"))
    if sold_entry is None or long_entry is None:
        return None, "missing entry price"
    sold_exit = _leg_exit_price(sold_leg)
    long_exit = _leg_exit_price(long_leg)
    exit_debit = None
    if sold_exit is not None and long_exit is not None:
        exit_debit = sold_exit - long_exit

    multipliers = {
        _positive_int(sold_leg.get("multiplier")),
        _positive_int(long_leg.get("multiplier")),
    }
    if len(multipliers) != 1 or None in multipliers:
        return None, "missing or mismatched lot size"
    lot_size = multipliers.pop()

    lots = None
    for item in record.get("summary") or []:
        if isinstance(item, dict):
            lots = _positive_int(item.get("lotsTraded"))
            if lots is not None:
                break
    if lots is None:
        lots = _positive_int(record.get("maxLots"))
    if lots is None:
        return None, "missing lot count"

    advice_id = record.get("_id")
    if not isinstance(advice_id, str) or not advice_id:
        return None, "missing id"
    entry_time = _parse_utc(record.get("createdAt"))
    if entry_time is None:
        return None, "missing or invalid entry time"
    pnl = _number(record.get("pnl"))
    if pnl is None:
        return None, "missing pnl"

    trade = ZenTrade(
        advice_id=advice_id,
        entry_time=entry_time,
        exit_time=_parse_utc(record.get("closedOn")),
        kind=sold.kind,
        sold_symbol=str(sold_leg["symbol"]),
        long_symbol=str(long_leg["symbol"]),
        sold_strike=sold.strike,
        long_strike=long.strike,
        width=abs(sold.strike - long.strike),
        expiry=sold.expiry,
        lots=lots,
        lot_size=lot_size,
        entry_credit=sold_entry - long_entry,
        exit_debit=exit_debit,
        pnl=pnl,
        margin=_number(record.get("marginRequired")),
        exit_class=_exit_class(record),
        sold_entry=sold_entry,
        long_entry=long_entry,
        sold_exit=sold_exit,
        long_exit=long_exit,
    )
    return trade, ""


def parse_trade(record: dict) -> ZenTrade | None:
    """Return the trade, or None if the record is not an executed, complete credit spread."""
    trade, _reason = _build(record)
    return trade


def rejection_reason(record: dict) -> str | None:
    """Return why parse_trade rejects a record, or None if it is accepted."""
    trade, reason = _build(record)
    return None if trade is not None else reason


def load_trades(path: Path) -> list[ZenTrade]:
    """Read an exported advices file and return accepted trades, oldest first."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("pastAdvices"), list):
        raise ValueError("expected an object with a pastAdvices list")
    trades = []
    for record in data["pastAdvices"]:
        trade = parse_trade(record)
        if trade is not None:
            trades.append(trade)
    return sorted(trades, key=lambda t: t.entry_time)


def _side_stats(trades: list[ZenTrade]) -> dict:
    return {"count": len(trades), "net": sum(t.pnl for t in trades)}


def summarize(trades: list[ZenTrade]) -> dict:
    """Aggregate results. Undefined ratios and averages are None, never zero."""
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    count = len(trades)
    return {
        "count": count,
        "wins": len(wins),
        "win_rate": len(wins) / count if count else None,
        "net": sum(pnls),
        "average_win": gross_win / len(wins) if wins else None,
        "average_loss": sum(losses) / len(losses) if losses else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "worst": min(pnls) if pnls else None,
        "calls": _side_stats([t for t in trades if t.kind == "CE"]),
        "puts": _side_stats([t for t in trades if t.kind == "PE"]),
    }
