"""Algo templates. Pure: a regime and a capital in, a strategy config out.

A template never talks to a broker. It returns a ``Plan`` that is either a
normal ``/strategy`` configuration (validated by the engine's own validator)
or a skip with the reason a trader can read. Orders, stops, recovery and the
Sandbox/Live switch all stay in ``services/strategy_module/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.algos.context import MarketInputs, RegimeResult

STRIKE_STEP = 50  # NIFTY strike gap in points
SHORT_OFFSET = "OTM1"
LONG_OFFSET = "OTM4"
SPREAD_WIDTH_PTS = 3 * STRIKE_STEP  # OTM1 to OTM4
MAX_ENGINE_LOTS = 50
DEFAULT_MAX_LOSS_PCT = 10.0
MIN_CONFIDENCE = 0.5
MORNING_GAP_MIN_PCT = 0.75  # smallest opening gap the morning algo acts on

#: Inputs used only to shape a strategy row at deploy time and to size the
#: worst case, never to trade. A 0.9 percent gap up is a representative day.
PLACEHOLDER_INPUTS = MarketInputs(gap_pct=0.9, open_gap_pct=0.9)


@dataclass(frozen=True)
class AlgoSpec:
    id: str
    name: str
    summary: str
    risk: str  # low | medium | high, for the catalogue badge
    allowed_labels: tuple[str, ...]
    min_confidence: float
    overnight: bool
    #: When the daily check runs, IST HH:MM. Overnight algos check late in the
    #: session; a morning algo checks once the opening gap is visible.
    entry_time: str = "15:05"
    #: "tested" or "experimental". Experimental means the indicative test below
    #: lost money, and the catalogue says so on the card.
    status: str = "tested"
    #: One plain sentence of what an indicative test of the rules found.
    evidence: str = ""


@dataclass(frozen=True)
class Plan:
    algo_id: str
    action: str  # trade | skip
    reason: str
    config: dict[str, Any] | None
    lots: int
    max_loss_inr: float | None
    side: str | None  # bull_put | bear_call | iron_condor


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
        status="experimental",
        evidence=(
            "Tested on real NSE option prices from 2023 to October 2026, after costs: lost "
            "money. Profit factor 0.54 over 434 nights, and a loss in every year. Before "
            "costs it earned about nothing, so costs decided the result."
        ),
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
        status="experimental",
        evidence=(
            "Tested on real NSE option prices from 2023 to October 2026, after costs: lost "
            "money. Profit factor 0.62 over 221 nights. Before costs it earned about nothing. "
            "Keep it in Sandbox mode."
        ),
    ),
    "morning_gap": AlgoSpec(
        id="morning_gap",
        name="Morning Gap Fade",
        summary=(
            "Intraday hedged credit spread on Nifty, entered at 09:25 after a large opening "
            "gap. Sells the side the gap moved towards, expecting it not to extend, and "
            "closes by 15:15 the same day. Skips expiry day and event days."
        ),
        risk="high",
        allowed_labels=("calm", "trending"),
        min_confidence=0.6,
        overnight=False,
        entry_time="09:25",
        status="experimental",
        evidence=(
            "Indicative test on Nifty data from 2018 to 2026 lost money: profit factor about "
            "0.7 on the years it was chosen on and about 0.5 on the later years it never saw "
            "(62 trades, a loss in every year). The opening gap and the overnight US move "
            "did not predict the rest of the day. Use it in Sandbox mode to study, not to trade."
        ),
    ),
    "calm_condor": AlgoSpec(
        id="calm_condor",
        name="Calm Condor",
        summary=(
            "Overnight iron condor on Nifty for quiet markets: sells both sides near the "
            "money and buys protection further out, to collect premium while the market "
            "drifts. Runs only on calm days, and stands aside the moment markets get "
            "directional or nervous. Exits next morning at 09:45."
        ),
        risk="medium",
        allowed_labels=("calm",),
        min_confidence=0.6,
        overnight=True,
        status="experimental",
        evidence=(
            "Tested on real NSE option prices from 2023 to October 2026, after costs: lost "
            "money. Profit factor 0.26 over 213 nights, and a loss in every year. Before costs "
            "it earned about nothing. An earlier model-based test showed a profit; real prices "
            "did not confirm it."
        ),
    ),
    "smart_pick": AlgoSpec(
        id="smart_pick",
        name="Smart Pick",
        summary=(
            "Does not have a trade of its own. Each afternoon it reads what kind of day it is "
            "and runs the one overnight algo whose past results on that kind of day were "
            "positive after costs in both the older and the newer years. If none qualifies it "
            "stands aside. Same protection, stop loss and next-morning exit as the algo it picks."
        ),
        risk="medium",
        allowed_labels=("calm", "trending", "volatile", "event"),
        min_confidence=MIN_CONFIDENCE,
        overnight=True,
        status="experimental",
        evidence=(
            "It only trades when an algo has earned the day. On the history tested when this was "
            "built, no algo had, so expect it to stand aside until one does. Rebuild its evidence "
            "table from the Algos page after new data arrives."
        ),
    ),
}


def _zen_side(bias: str) -> str:
    return "bear_call" if bias == "bearish" else "bull_put"


def _opposite(side: str) -> str:
    return "bull_put" if side == "bear_call" else "bear_call"


def spread_config(
    name: str,
    side: str,
    lots: int,
    expiry: str,
    *,
    intraday: bool = False,
    short_offset: str = SHORT_OFFSET,
    long_offset: str = LONG_OFFSET,
) -> dict[str, Any]:
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
        "strategy_type": "intraday" if intraday else "positional",
        "entry_time": "09:25" if intraday else None,
        "exit_time": "15:15" if intraday else "09:45",
        "product": "MIS" if intraday else "NRML",
        "pricetype": "MARKET",
        # Protection first, so the short never sits naked while the hedge is
        # still working.
        "legs": [
            leg(1, "B", long_offset),
            leg(2, "S", short_offset, sl_pts=30, target_pts=90, risk_unit="percent"),
        ],
    }


CONDOR_SHORT_OFFSET = "OTM2"
CONDOR_LONG_OFFSET = "OTM5"
CONDOR_SL_PCT = 50
CONDOR_TARGET_PCT = 70


def condor_config(
    name: str,
    lots: int,
    expiry: str,
    *,
    short_offset: str = CONDOR_SHORT_OFFSET,
    long_offset: str = CONDOR_LONG_OFFSET,
) -> dict[str, Any]:
    def leg(leg_id: int, position: str, option_type: str, offset: str, **risk: Any):
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

    short_risk = {"sl_pts": CONDOR_SL_PCT, "target_pts": CONDOR_TARGET_PCT, "risk_unit": "percent"}
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
        # Both protective legs first, so neither short sits naked.
        "legs": [
            leg(1, "B", "PE", long_offset),
            leg(2, "B", "CE", long_offset),
            leg(3, "S", "PE", short_offset, **short_risk),
            leg(4, "S", "CE", short_offset, **short_risk),
        ],
    }


#: Algos the trader built, by catalogue id. Filled by ``builder.register``; read by ``build``.
CUSTOM_SPECS: dict[str, Any] = {}


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
    inputs: MarketInputs | None = None,
) -> Plan:
    """Turn a regime into a plan. Raises ``KeyError`` for an unknown algo.

    ``inputs`` is the raw market snapshot. Only the morning algo reads it, for
    the opening gap, which the regime label alone does not carry.
    """
    spec = ALGOS[algo_id]
    if algo_id == "smart_pick":
        from services.algos import chooser_store

        return chooser_store.smart_plan(
            regime,
            capital=capital,
            lot_size=lot_size,
            days_to_expiry=days_to_expiry,
            max_loss_pct=max_loss_pct,
            inputs=inputs,
        )
    if algo_id in CUSTOM_SPECS:
        from services.algos import builder

        return builder.live_plan(
            CUSTOM_SPECS[algo_id],
            algo_id,
            spec.name,
            regime,
            capital=capital,
            lot_size=lot_size,
            days_to_expiry=days_to_expiry,
            max_loss_pct=max_loss_pct,
        )

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

    if spec.overnight and days_to_expiry is not None and days_to_expiry <= 1:
        # Rolling to next week's expiry for one night earns almost no time decay
        # and pays full costs. Skipping these days beat rolling in every matched
        # pair of a 50-configuration test, on the years it was chosen on and the
        # later years it never saw.
        return _skip(
            algo_id,
            f"Expiry is today or tomorrow, so {spec.name} waits: next week's options earn "
            "too little time decay for one night.",
        )

    gap = inputs.open_gap_pct if inputs is not None else None
    if algo_id == "morning_gap":
        if gap is None:
            return _skip(algo_id, "The opening gap is not available yet.")
        if days_to_expiry == 0:
            return _skip(algo_id, f"Today is expiry day, so {spec.name} does not trade.")
        if abs(gap) < MORNING_GAP_MIN_PCT:
            return _skip(
                algo_id,
                f"The opening gap of {gap:+.2f} percent is too small to trade "
                f"({spec.name} needs {MORNING_GAP_MIN_PCT} percent or more).",
            )
        # Fade: sell the side the gap moved towards, expecting it not to extend.
        side = "bear_call" if gap > 0 else "bull_put"
    elif algo_id == "calm_condor":
        side = "iron_condor"
    else:
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

    expiry = "weekly"
    if side == "iron_condor":
        label = "Iron Condor"
        config = condor_config(f"{spec.name} - {label}", lots, expiry)
    else:
        label = "Bull Put Spread" if side == "bull_put" else "Bear Call Spread"
        config = spread_config(
            f"{spec.name} - {label}", side, lots, expiry, intraday=algo_id == "morning_gap"
        )
    max_loss = float(lots * loss_per_lot)
    config["daily_loss_limit_inr"] = max_loss
    if algo_id == "morning_gap":
        reason = f"Opening gap of {gap:+.2f} percent: {label.lower()}."
    else:
        reason = f"{regime.label.capitalize()} market, {regime.bias} bias: {label.lower()}."

    return Plan(
        algo_id=algo_id,
        action="trade",
        reason=reason,
        config=config,
        lots=lots,
        max_loss_inr=max_loss,
        side=side,
    )


def coverage(
    *, capital: float = 500_000, lot_size: int = 75, days_to_expiry: int | None = 4
) -> dict[str, Any]:
    """Which algos trade in which market regimes, from the real build rules.

    Reports what the catalogue will actually do, so a gap is visible rather than
    assumed away. A regime with no algo is a day the platform stands aside.
    """
    labels = ("calm", "trending", "volatile", "event")
    matrix: dict[str, list[str]] = {}
    for label in labels:
        regime = RegimeResult(
            label=label, bias="neutral", score=0.0, confidence=1.0, reasons=(), missing=()
        )
        matrix[label] = [
            algo_id
            for algo_id in ALGOS
            if build(
                algo_id,
                regime,
                capital=capital,
                lot_size=lot_size,
                days_to_expiry=days_to_expiry,
                inputs=PLACEHOLDER_INPUTS,
            ).action
            == "trade"
        ]
    return {
        "regimes": matrix,
        "stands_aside_on": [label for label, algos in matrix.items() if not algos],
    }
