"""Market regime scoring. Pure: no I/O, no clock, no logging.

Every input arrives as an argument and the decision leaves as a return value,
so the same inputs always give the same regime and the scorer is tested with
fixed numbers. A missing input is named in ``missing`` and lowers
``confidence``; it is never read as zero.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Weight of each directional cue and the sign it pushes with. Crude and the
#: dollar index rising are headwinds for Indian equities, so they push down.
_CUES: tuple[tuple[str, float], ...] = (
    ("gap_pct", 0.40),
    ("sp500_pct", 0.20),
    ("nasdaq_pct", 0.10),
    ("crude_pct", -0.10),
    ("dxy_pct", -0.10),
    ("nifty_vs_ma20_pct", 0.10),
)
#: Volatility inputs carry confidence but no direction.
_VOL_WEIGHT = 0.20
_CUE_CLIP = 2.0
_BIAS_EDGE = 0.15
_TREND_SCORE = 0.30

EVENT_GAP_PCT = 1.2
EVENT_VIX = 28.0
VOLATILE_VIX = 20.0
VOLATILE_VIX_JUMP_PCT = 8.0
VOLATILE_GLOBAL_PCT = 2.0
TREND_GAP_PCT = 0.4


@dataclass(frozen=True)
class MarketInputs:
    """Percent changes are in percent (0.4 means 0.4 percent)."""

    gap_pct: float | None = None
    sp500_pct: float | None = None
    nasdaq_pct: float | None = None
    crude_pct: float | None = None
    dxy_pct: float | None = None
    vix: float | None = None
    vix_change_pct: float | None = None
    nifty_vs_ma20_pct: float | None = None
    #: Today's open against the previous close. Not scored; read by the morning
    #: algo, which needs the opening gap and not the move since the open.
    open_gap_pct: float | None = None


@dataclass(frozen=True)
class RegimeResult:
    label: str  # calm | trending | volatile | event
    bias: str  # bullish | bearish | neutral
    score: float  # -1 (bearish) .. +1 (bullish)
    confidence: float  # share of inputs that were available, 0..1
    reasons: tuple[str, ...]
    missing: tuple[str, ...]


def _clip(value: float) -> float:
    return max(-_CUE_CLIP, min(_CUE_CLIP, value)) / _CUE_CLIP


def score_regime(inputs: MarketInputs) -> RegimeResult:
    """Classify the market from one snapshot of inputs."""
    missing: list[str] = []
    weighted = 0.0
    used = 0.0
    total = sum(abs(w) for _, w in _CUES) + _VOL_WEIGHT

    for name, weight in _CUES:
        value = getattr(inputs, name)
        if value is None:
            missing.append(name)
            continue
        weighted += _clip(value) * weight
        used += abs(weight)

    vix_known = inputs.vix is not None
    if inputs.vix is None:
        missing.append("vix")
    if inputs.vix_change_pct is None:
        missing.append("vix_change_pct")
    if vix_known:
        used += _VOL_WEIGHT

    score = weighted / used if used else 0.0
    score = max(-1.0, min(1.0, score))
    confidence = round(used / total, 4) if total else 0.0

    if score > _BIAS_EDGE:
        bias = "bullish"
    elif score < -_BIAS_EDGE:
        bias = "bearish"
    else:
        bias = "neutral"

    reasons: list[str] = []
    gap = inputs.gap_pct
    vix = inputs.vix
    jump = inputs.vix_change_pct
    globals_ = [v for v in (inputs.sp500_pct, inputs.nasdaq_pct) if v is not None]

    label = "calm"
    if (gap is not None and abs(gap) > EVENT_GAP_PCT) or (vix is not None and vix > EVENT_VIX):
        label = "event"
        if gap is not None and abs(gap) > EVENT_GAP_PCT:
            reasons.append(f"Opening gap of {gap:+.2f} percent is unusually large")
        if vix is not None and vix > EVENT_VIX:
            reasons.append(f"India VIX at {vix:.1f} signals stress")
    elif (
        (vix is not None and vix > VOLATILE_VIX)
        or (jump is not None and jump > VOLATILE_VIX_JUMP_PCT)
        or any(abs(v) > VOLATILE_GLOBAL_PCT for v in globals_)
    ):
        label = "volatile"
        if vix is not None and vix > VOLATILE_VIX:
            reasons.append(f"India VIX at {vix:.1f} is elevated")
        if jump is not None and jump > VOLATILE_VIX_JUMP_PCT:
            reasons.append(f"India VIX is up {jump:.1f} percent")
        if any(abs(v) > VOLATILE_GLOBAL_PCT for v in globals_):
            reasons.append("A large overnight move in US indices")
    elif (gap is not None and abs(gap) > TREND_GAP_PCT) or abs(score) >= _TREND_SCORE:
        label = "trending"
        reasons.append(
            f"Cues point {'up' if score > 0 else 'down'}"
            + (f" with a {gap:+.2f} percent gap" if gap is not None else "")
        )
    else:
        reasons.append("No large gap, no volatility spike and mixed or flat global cues")

    if missing:
        reasons.append("Missing inputs: " + ", ".join(missing))

    return RegimeResult(
        label=label,
        bias=bias,
        score=round(score, 4),
        confidence=confidence,
        reasons=tuple(reasons),
        missing=tuple(missing),
    )
