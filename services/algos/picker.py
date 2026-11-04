"""Strategy picker: every option structure, priced live, with what it costs, risks and needs.

The trader chooses. This module never names a pick, never places or registers anything and never claims a
forecast. For each structure it reports, from the live chain: the premium, the most it can earn and lose at
expiry, the breakevens, the capital it needs, the round-trip costs, and a fit score for how well today's
conditions (trend, volatility, time of day, days to expiry, liquidity, size against the loss cap) match the
structure's design. A structure that cannot be taken inside the trader's own limits is listed as blocked with
the reason, never hidden.

Pure: no I/O, no clock, no logging. ``services/algos/picker_inputs.py`` gathers the inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from services.algos.costs import REALISTIC
from services.algos.mandate import Mandate

DISCLAIMER = (
    "The fit score is how well today's conditions match each structure's design. It is not a forecast of "
    "profit. The evidence column says what has actually been tested, and for most structures that is nothing."
)

STRIKE_STEP = 50  # Nifty strike gap in points
OPEN_MINUTES = 375  # 09:15 to 15:30
FIRST_MINUTES = 5
LAST_MINUTES = 15
MINUTES_PER_YEAR = OPEN_MINUTES * 252

WEIGHTS = {
    "direction": 0.25,
    "volatility": 0.20,
    "risk": 0.20,
    "liquidity": 0.15,
    "time": 0.10,
    "dte": 0.10,
}


@dataclass(frozen=True)
class Leg:
    kind: str  # CE | PE
    offset: int  # strikes from the money: +1 is one strike above
    side: str  # B | S
    qty: int = 1


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    legs: tuple[Leg, ...]
    direction: str  # bullish | bearish | neutral | any
    vol: str  # long | short | flat  (buys or sells premium)
    window: tuple[int, int]  # minutes after the open when the design suits best
    dte: tuple[int, int]  # days to expiry when it suits best


def _t(id_, name, legs, direction, vol, window, dte):
    return Template(id_, name, tuple(Leg(*leg) for leg in legs), direction, vol, window, dte)


MORNING = (10, 150)
DAY = (15, 300)
TEMPLATES: tuple[Template, ...] = (
    _t("long_call", "Long Call", [("CE", 0, "B")], "bullish", "long", MORNING, (2, 10)),
    _t("long_put", "Long Put", [("PE", 0, "B")], "bearish", "long", MORNING, (2, 10)),
    _t("short_call", "Short Call", [("CE", 1, "S")], "bearish", "short", DAY, (0, 5)),
    _t("short_put", "Short Put", [("PE", -1, "S")], "bullish", "short", DAY, (0, 5)),
    _t(
        "bull_call_spread",
        "Bull Call Spread",
        [("CE", 0, "B"), ("CE", 3, "S")],
        "bullish",
        "flat",
        MORNING,
        (1, 8),
    ),
    _t(
        "bear_put_spread",
        "Bear Put Spread",
        [("PE", 0, "B"), ("PE", -3, "S")],
        "bearish",
        "flat",
        MORNING,
        (1, 8),
    ),
    _t(
        "bull_put_spread",
        "Bull Put Spread",
        [("PE", -1, "S"), ("PE", -4, "B")],
        "bullish",
        "short",
        DAY,
        (0, 6),
    ),
    _t(
        "bear_call_spread",
        "Bear Call Spread",
        [("CE", 1, "S"), ("CE", 4, "B")],
        "bearish",
        "short",
        DAY,
        (0, 6),
    ),
    _t(
        "long_straddle",
        "Long Straddle",
        [("CE", 0, "B"), ("PE", 0, "B")],
        "any",
        "long",
        MORNING,
        (2, 10),
    ),
    _t(
        "short_straddle",
        "Short Straddle",
        [("CE", 0, "S"), ("PE", 0, "S")],
        "neutral",
        "short",
        DAY,
        (0, 4),
    ),
    _t(
        "long_strangle",
        "Long Strangle",
        [("CE", 2, "B"), ("PE", -2, "B")],
        "any",
        "long",
        MORNING,
        (2, 10),
    ),
    _t(
        "short_strangle",
        "Short Strangle",
        [("CE", 2, "S"), ("PE", -2, "S")],
        "neutral",
        "short",
        DAY,
        (0, 5),
    ),
    _t(
        "short_iron_condor",
        "Short Iron Condor",
        [("PE", -4, "B"), ("PE", -2, "S"), ("CE", 2, "S"), ("CE", 4, "B")],
        "neutral",
        "short",
        DAY,
        (0, 6),
    ),
    _t(
        "long_iron_condor",
        "Long Iron Condor",
        [("PE", -4, "S"), ("PE", -2, "B"), ("CE", 2, "B"), ("CE", 4, "S")],
        "any",
        "long",
        MORNING,
        (2, 10),
    ),
    _t(
        "short_iron_fly",
        "Short Iron Fly",
        [("PE", -3, "B"), ("PE", 0, "S"), ("CE", 0, "S"), ("CE", 3, "B")],
        "neutral",
        "short",
        DAY,
        (0, 6),
    ),
    _t(
        "long_iron_fly",
        "Long Iron Fly",
        [("PE", -3, "S"), ("PE", 0, "B"), ("CE", 0, "B"), ("CE", 3, "S")],
        "any",
        "long",
        MORNING,
        (2, 10),
    ),
    _t(
        "call_butterfly",
        "Call Butterfly",
        [("CE", -2, "B"), ("CE", 0, "S", 2), ("CE", 2, "B")],
        "neutral",
        "short",
        DAY,
        (0, 6),
    ),
    _t(
        "put_butterfly",
        "Put Butterfly",
        [("PE", 2, "B"), ("PE", 0, "S", 2), ("PE", -2, "B")],
        "neutral",
        "short",
        DAY,
        (0, 6),
    ),
    _t(
        "call_ratio_spread",
        "Call Ratio Spread",
        [("CE", 0, "B"), ("CE", 2, "S", 2)],
        "neutral",
        "short",
        DAY,
        (0, 6),
    ),
    _t(
        "put_ratio_spread",
        "Put Ratio Spread",
        [("PE", 0, "B"), ("PE", -2, "S", 2)],
        "neutral",
        "short",
        DAY,
        (0, 6),
    ),
    _t(
        "call_ratio_back_spread",
        "Call Ratio Back Spread",
        [("CE", 0, "S"), ("CE", 2, "B", 2)],
        "bullish",
        "long",
        MORNING,
        (2, 10),
    ),
    _t(
        "put_ratio_back_spread",
        "Put Ratio Back Spread",
        [("PE", 0, "S"), ("PE", -2, "B", 2)],
        "bearish",
        "long",
        MORNING,
        (2, 10),
    ),
    _t(
        "jade_lizard",
        "Jade Lizard",
        [("PE", -2, "S"), ("CE", 1, "S"), ("CE", 2, "B")],
        "neutral",
        "short",
        DAY,
        (0, 6),
    ),
    _t(
        "long_synthetic",
        "Long Synthetic",
        [("CE", 0, "B"), ("PE", 0, "S")],
        "bullish",
        "flat",
        MORNING,
        (1, 8),
    ),
    _t(
        "short_synthetic",
        "Short Synthetic",
        [("CE", 0, "S"), ("PE", 0, "B")],
        "bearish",
        "flat",
        MORNING,
        (1, 8),
    ),
)

#: What has actually been tested here. Anything not listed is untested, and that is stated.
EVIDENCE = {
    "bear_call_spread": "Forward test running in Sandbox (weekly call spread, S3n): no result yet. Not shown to earn.",
    "short_iron_condor": "Replayed on 108 weekly expiries: no edge after costs.",
    "short_iron_fly": "Replayed in the condor family on 108 weekly expiries: no edge after costs.",
}
UNTESTED = "Untested: no evidence either way."


def template(template_id: str) -> Template:
    for item in TEMPLATES:
        if item.id == template_id:
            return item
    raise KeyError(template_id)


@dataclass(frozen=True)
class Conditions:
    bias: str
    bias_score: float | None
    regime_label: str | None
    regime_confidence: float
    vix: float | None
    vix_change_pct: float | None
    minutes_since_open: int
    dte: int
    spot: float
    step: int
    lot: int
    momentum_pct: float | None = None


@dataclass(frozen=True)
class PricedLeg:
    kind: str
    strike: float
    side: str
    qty: int
    bid: float
    ask: float

    @property
    def price(self) -> float:
        """Mid price, the reference for payoff; the spread is costed separately."""
        return (self.bid + self.ask) / 2.0


def price_legs(
    tpl: Template, spot: float, step: int, chain: dict[tuple[str, float], dict[str, Any]]
) -> list[PricedLeg] | None:
    """Price every leg from the chain, or None when a strike is missing or has no two-sided quote."""
    atm = round(spot / step) * step
    legs: list[PricedLeg] = []
    for leg in tpl.legs:
        strike = float(atm + leg.offset * step)
        quote = chain.get((leg.kind, strike))
        if not quote:
            return None
        bid, ask = float(quote.get("bid") or 0), float(quote.get("ask") or 0)
        if bid <= 0 or ask <= 0 or ask < bid:
            return None
        legs.append(PricedLeg(leg.kind, strike, leg.side, leg.qty, bid, ask))
    return legs


def _payoff_pts(legs: list[PricedLeg], s: float) -> float:
    total = 0.0
    for leg in legs:
        intrinsic = max(s - leg.strike, 0.0) if leg.kind == "CE" else max(leg.strike - s, 0.0)
        sign = 1.0 if leg.side == "B" else -1.0
        total += sign * leg.qty * (intrinsic - leg.price)
    return total


def payoff_stats(legs: list[PricedLeg], lot: int) -> dict[str, Any]:
    """Expiry payoff in rupees for one lot: piecewise linear, so its corners are at the strikes."""
    strikes = sorted({leg.strike for leg in legs})
    top = strikes[-1] * 3.0
    points = [0.0, *strikes, top]
    values = [_payoff_pts(legs, p) for p in points]
    call_slope = sum((1 if leg.side == "B" else -1) * leg.qty for leg in legs if leg.kind == "CE")
    unbounded_loss = call_slope < 0
    unbounded_profit = call_slope > 0
    worst = min(values[:-1]) if unbounded_loss else min(values)
    best = max(values[:-1]) if unbounded_profit else max(values)
    net_pts = sum(
        (leg.qty * leg.price) * (1 if leg.side == "S" else -1) for leg in legs
    )  # positive is a credit
    breakevens: list[float] = []
    for a, b, va, vb in zip(points, points[1:], values, values[1:], strict=False):
        if va == 0 and a not in breakevens and a > 0:
            breakevens.append(a)
        if (va < 0 < vb) or (vb < 0 < va):
            breakevens.append(a + (b - a) * (-va) / (vb - va))
    breakevens = sorted({round(x, 2) for x in breakevens})
    return {
        "max_loss": None if unbounded_loss else round(-worst * lot, 2) if worst < 0 else 0.0,
        "unbounded_loss": unbounded_loss,
        "max_profit": None if unbounded_profit else round(best * lot, 2),
        "net_credit": round(net_pts * lot, 2),
        "breakevens": breakevens,
    }


def round_trip_costs(legs: list[PricedLeg], lot: int) -> dict[str, float]:
    """Charges and the spread given up for entering and leaving once, at the mid-price reference."""
    c = REALISTIC
    orders = 2 * len(legs)
    turnover = 0.0
    sell_premium_exit = 0.0
    buy_premium_entry = 0.0
    spread = 0.0
    for leg in legs:
        units = leg.qty * lot
        turnover += 2 * leg.price * units  # entry and exit at the same reference price
        spread += (leg.ask - leg.bid) * units
        if leg.side == "B":
            sell_premium_exit += leg.price * units  # the bought option is sold at exit
            buy_premium_entry += leg.price * units
        else:
            sell_premium_exit += 0.0
    sells = sum(leg.price * leg.qty * lot for leg in legs if leg.side == "S")
    sold_total = sells + sell_premium_exit
    brokerage = orders * c.brokerage_per_order
    stt = sold_total * c.stt_after
    exchange = turnover * c.exchange_pct
    sebi = turnover * c.sebi_pct
    gst = c.gst * (brokerage + exchange + sebi)
    stamp = (
        buy_premium_entry * c.stamp_pct
        + sum(leg.price * leg.qty * lot for leg in legs if leg.side == "S") * c.stamp_pct
    )
    charges = brokerage + stt + exchange + sebi + gst + stamp
    return {
        "charges": round(charges, 2),
        "spread": round(spread, 2),
        "total": round(charges + spread, 2),
    }


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _direction_fit(tpl: Template, c: Conditions) -> float:
    if tpl.direction == "any":
        return 0.5
    bias = c.bias_score if c.bias_score is not None else 0.0
    mom = _clip((c.momentum_pct or 0.0) / 0.5)
    s = _clip(0.6 * bias + 0.4 * mom)
    if tpl.direction == "bullish":
        return (s + 1) / 2
    if tpl.direction == "bearish":
        return (1 - s) / 2
    return 1 - abs(s)


def _vol_fit(tpl: Template, c: Conditions) -> float:
    if c.vix is None:
        return 0.5
    level = _clip((c.vix - 12.0) / 12.0, 0.0, 1.0)  # 0 cheap, 1 rich
    trend = _clip((c.vix_change_pct or 0.0) / 10.0)
    stressed = 1.0 if c.regime_label in ("volatile", "event") else 0.0
    calm = 1.0 if c.regime_label == "calm" else 0.0
    if tpl.vol == "long":
        return 0.5 * (1 - level) + 0.25 * (trend + 1) / 2 + 0.25 * stressed
    if tpl.vol == "short":
        return 0.5 * level + 0.25 * (1 - trend) / 2 + 0.25 * calm
    return 0.6


def _time_fit(tpl: Template, c: Conditions) -> float:
    m = c.minutes_since_open
    if m < 0 or m > OPEN_MINUTES:
        return 0.0
    if m < FIRST_MINUTES or m > OPEN_MINUTES - LAST_MINUTES:
        return 0.2
    lo, hi = tpl.window
    return 1.0 if lo <= m <= hi else 0.5


def _dte_fit(tpl: Template, c: Conditions) -> float:
    lo, hi = tpl.dte
    if lo <= c.dte <= hi:
        return 1.0
    gap = lo - c.dte if c.dte < lo else c.dte - hi
    return max(0.0, 1.0 - 0.15 * gap)


def expected_moves(vix: float | None, spot: float) -> dict[str, float | None]:
    """One standard deviation of Nifty over 15 minutes and over a day, from India VIX."""
    if vix is None:
        return {"fifteen_minutes": None, "day": None}
    sigma = vix / 100.0
    return {
        "fifteen_minutes": round(spot * sigma * math.sqrt(15 / MINUTES_PER_YEAR), 1),
        "day": round(spot * sigma * math.sqrt(1 / 252), 1),
    }


def rank(
    cond: Conditions,
    chain: dict[tuple[str, float], dict[str, Any]],
    mandate: Mandate,
    margins: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Score every structure. ``margins`` maps template id to the broker's margin, when it was fetched."""
    margins = margins or {}
    ranked: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    notes: list[str] = []
    if cond.minutes_since_open < 0 or cond.minutes_since_open > OPEN_MINUTES:
        notes.append(
            "The market is closed, so prices are the last traded ones and the time score is zero."
        )
    if cond.vix is None:
        notes.append("No data for: India VIX. Volatility fit is neutral.")
    if cond.regime_confidence < 0.5:
        notes.append("Few market inputs were available, so the trend reading is a weak one.")

    for tpl in TEMPLATES:
        legs = price_legs(tpl, cond.spot, cond.step, chain)
        row: dict[str, Any] = {
            "id": tpl.id,
            "name": tpl.name,
            "direction": tpl.direction,
            "legs": [
                {"kind": leg.kind, "offset": leg.offset, "side": leg.side, "qty": leg.qty}
                for leg in tpl.legs
            ],
            "evidence": EVIDENCE.get(tpl.id, UNTESTED),
            "priced": legs is not None,
            "blocked_because": [],
        }
        if legs is None:
            row["blocked_because"].append("No two-sided live quote for one of its strikes.")
            blocked.append(row)
            continue
        stats = payoff_stats(legs, cond.lot)
        costs = round_trip_costs(legs, cond.lot)
        margin = margins.get(tpl.id)
        if margin is not None:
            capital, source = margin, "broker"
        elif stats["max_loss"] is not None and stats["net_credit"] <= 0:
            capital, source = -stats["net_credit"], "premium paid"
        elif stats["max_loss"] is not None:
            capital, source = stats["max_loss"], "worst loss (estimate)"
        else:
            capital, source = None, "not available"
        row.update(
            stats=stats,
            costs=costs,
            capital_required=None if capital is None else round(capital, 2),
            capital_source=source,
        )
        reasons: list[str] = []
        if stats["unbounded_loss"]:
            reasons.append("Loss is unlimited, which no daily cap can contain.")
        elif stats["max_loss"] is not None and stats["max_loss"] > mandate.max_daily_loss:
            reasons.append(
                f"Worst loss Rs {stats['max_loss']:,.0f} is above your daily cap of Rs {mandate.max_daily_loss:,.0f}."
            )
        if capital is not None and capital > mandate.capital:
            reasons.append(
                f"Needs Rs {capital:,.0f}, more than your capital of Rs {mandate.capital:,.0f}."
            )
        gross = sum(leg.price * leg.qty for leg in legs) * cond.lot
        cost_ratio = costs["total"] / gross if gross else 1.0
        loss_ratio = (
            0.0
            if stats["max_loss"] is None
            else stats["max_loss"] / mandate.max_daily_loss
            if mandate.max_daily_loss
            else 1.0
        )
        components = {
            "direction": round(_direction_fit(tpl, cond), 3),
            "volatility": round(_vol_fit(tpl, cond), 3),
            "risk": round(max(0.0, 1.0 - 0.7 * min(loss_ratio, 1.0)), 3),
            "liquidity": round(1.0 - _clip(cost_ratio / 0.10, 0.0, 1.0), 3),
            "time": round(_time_fit(tpl, cond), 3),
            "dte": round(_dte_fit(tpl, cond), 3),
        }
        row["components"] = components
        row["score"] = round(100.0 * sum(WEIGHTS[k] * v for k, v in components.items()), 1)
        if reasons:
            row["blocked_because"] = reasons
            blocked.append(row)
        else:
            ranked.append(row)

    ranked.sort(key=lambda r: r["score"], reverse=True)
    blocked.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    return {
        "header": {
            "disclaimer": DISCLAIMER,
            "notes": notes,
            "confidence": round(cond.regime_confidence, 2),
            "expected_move": expected_moves(cond.vix, cond.spot),
            "capital": mandate.capital,
            "daily_cap": mandate.max_daily_loss,
            "lot": cond.lot,
            "spot": cond.spot,
            "dte": cond.dte,
        },
        "ranked": ranked,
        "blocked": blocked,
    }
