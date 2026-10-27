"""Algo templates. Pure: a regime and a capital in, a strategy config out.

A template never talks to a broker. It returns a ``Plan`` that is either a
normal ``/strategy`` configuration (validated by the engine's own validator)
or a skip with the reason a trader can read. Orders, stops, recovery and the
Sandbox/Live switch all stay in ``services/strategy_module/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.algos.context import RegimeResult

STRIKE_STEP = 50  # NIFTY strike gap in points
SHORT_OFFSET = "OTM1"
LONG_OFFSET = "OTM4"
SPREAD_WIDTH_PTS = 3 * STRIKE_STEP  # OTM1 to OTM4
MAX_ENGINE_LOTS = 50
DEFAULT_MAX_LOSS_PCT = 10.0
MIN_CONFIDENCE = 0.5


@dataclass(frozen=True)
class AlgoSpec:
    id: str
    name: str
    summary: str
    risk: str  # low | medium | high, for the catalogue badge
    allowed_labels: tuple[str, ...]
    min_confidence: float
    overnight: bool


@dataclass(frozen=True)
class Plan:
    algo_id: str
    action: str  # trade | skip
    reason: str
    config: dict[str, Any] | None
    lots: int
    max_loss_inr: float | None
    side: str | None  # bull_put | bear_call


ALGOS: dict[str, AlgoSpec] = {
    "zen": AlgoSpec(
        id="zen",
        name="Zen",
        summary=(
            "Overnight hedged credit spread on Nifty. Sells a near strike, buys a far one "
            "as protection, on the side today's market favours. Stop loss 30 percent of "
            "premium, target 90 percent (1 to 3). Exits next morning at 09:45."
        ),
        risk="medium",
        allowed_labels=("calm", "trending"),
        min_confidence=MIN_CONFIDENCE,
        overnight=True,
    ),
    "mirror_zen": AlgoSpec(
        id="mirror_zen",
        name="Mirror Zen",
        summary=(
            "The opposite-side twin of Zen, run only on trending days so the pair hedges "
            "direction. Same protection, stop loss and next-morning exit."
        ),
        risk="medium",
        allowed_labels=("trending",),
        min_confidence=0.6,
        overnight=True,
    ),
}


def _zen_side(bias: str) -> str:
    return "bear_call" if bias == "bearish" else "bull_put"


def _opposite(side: str) -> str:
    return "bull_put" if side == "bear_call" else "bear_call"


def _spread_config(name: str, side: str, lots: int, expiry: str) -> dict[str, Any]:
    option_type = "PE" if side == "bull_put" else "CE"

    def leg(leg_id: int, position: str, offset: str, **risk: Any) -> dict[str, Any]:
        return {
            "id": leg_id,
            "segment": "options",
            "position": position,
            "lots": lots,
            "option_type": option_type,
            "strike_mode": "atm",
            "atm_offset": offset,
            "expiry": expiry,
            **risk,
        }

    return {
        "name": name,
        "strategy_kind": "batch",
        "universe_tab": "weekly_monthly",
        "underlying": "NIFTY",
        "underlying_exchange": "NSE_INDEX",
        "strategy_type": "positional",
        "entry_time": None,
        "exit_time": "09:45",
        "product": "NRML",
        "pricetype": "MARKET",
        # Protection first, so the short never sits naked while the hedge is
        # still working.
        "legs": [
            leg(1, "B", LONG_OFFSET),
            leg(2, "S", SHORT_OFFSET, sl_pts=30, target_pts=90, risk_unit="percent"),
        ],
    }


def _skip(algo_id: str, reason: str) -> Plan:
    return Plan(algo_id, "skip", reason, None, 0, None, None)


def build(
    algo_id: str,
    regime: RegimeResult,
    *,
    capital: float,
    lot_size: int,
    days_to_expiry: int | None,
    max_loss_pct: float = DEFAULT_MAX_LOSS_PCT,
) -> Plan:
    """Turn a regime into a plan. Raises ``KeyError`` for an unknown algo."""
    spec = ALGOS[algo_id]

    if regime.label not in spec.allowed_labels:
        return _skip(
            algo_id,
            f"{spec.name} does not trade a {regime.label} market. "
            f"It runs on: {', '.join(spec.allowed_labels)}.",
        )
    if regime.confidence < spec.min_confidence:
        return _skip(
            algo_id,
            f"Market data confidence is too low ({regime.confidence:.0%} of inputs "
            f"available, {spec.name} needs {spec.min_confidence:.0%}).",
        )

    zen_side = _zen_side(regime.bias)
    side = zen_side if algo_id == "zen" else _opposite(zen_side)

    loss_per_lot = SPREAD_WIDTH_PTS * lot_size
    lots = int((capital * max_loss_pct / 100.0) // loss_per_lot)
    lots = min(lots, MAX_ENGINE_LOTS)
    if lots < 1:
        need = loss_per_lot * 100.0 / max_loss_pct
        return _skip(
            algo_id,
            f"Capital is too small for one lot with a {max_loss_pct:.0f} percent loss "
            f"limit. {spec.name} needs about {need:,.0f} rupees.",
        )

    expiry = "next_week" if days_to_expiry is not None and days_to_expiry <= 1 else "weekly"
    label = "Bull Put Spread" if side == "bull_put" else "Bear Call Spread"
    config = _spread_config(f"{spec.name} - {label}", side, lots, expiry)
    max_loss = float(lots * loss_per_lot)
    config["daily_loss_limit_inr"] = max_loss

    return Plan(
        algo_id=algo_id,
        action="trade",
        reason=f"{regime.label.capitalize()} market, {regime.bias} bias: {label.lower()}.",
        config=config,
        lots=lots,
        max_loss_inr=max_loss,
        side=side,
    )
