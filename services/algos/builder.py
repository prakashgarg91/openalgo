"""Build an algo from a few choices and let a search refine it, without fooling itself.

A search over many configurations always finds one that looked good on the data it
was shown. So the search here is walk-forward and its rules are fixed in code:

- the history is cut in time into train (first half), validate (next quarter) and
  test (last quarter);
- every configuration is scored on train alone, after costs, as net result minus half
  its worst drawdown (a profit that needed a deep hole to get is worth less);
- the best few on train are re-scored on validate, and the winner is the best of those;
- only the winner is then read on test, which nothing was chosen on;
- the verdict is "edge shown" only if the winner holds up on validate AND test with
  enough trades, and even then it is one holdout, not proof.

The number of configurations tried is reported with the result, together with how
many of them lost money on the test period, so the selection effect is visible.

This module does no I/O. The caller supplies ``run``, which replays one configuration
and returns its trades (``date`` and ``pnl`` per lot).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from services.algos.context import RegimeResult
from services.algos.lab import summarize
from services.algos.templates import (
    DEFAULT_MAX_LOSS_PCT,
    MAX_ENGINE_LOTS,
    STRIKE_STEP,
    Plan,
    condor_config,
    spread_config,
)

FAMILIES = ("condor", "bull_put", "bear_call")
SHAPES = ((1, 3), (1, 4), (2, 4), (2, 5), (3, 5))  # (short OTM, long OTM)
LABEL_SETS = (("calm",), ("calm", "trending"))
EXPIRY_HANDLING = ("skip", "roll")
VALID_LABELS = ("calm", "trending", "volatile", "event")
MIN_CONFIDENCE = 0.5
MAX_TRIALS = 90

# Fixed before any search runs.
TRAIN_SHARE, VALIDATE_SHARE = 0.50, 0.25
MIN_TRAIN_TRADES = 60
TOP_ON_TRAIN = 5
MIN_EVAL_TRADES = 60
MIN_PROFIT_FACTOR = 1.35
MIN_VALIDATE_PROFIT_FACTOR = 1.2
DRAWDOWN_WEIGHT = 0.5


class SpecError(ValueError):
    """A stored or submitted spec is not one the builder can run."""


@dataclass(frozen=True)
class Spec:
    family: str
    short: int
    long: int
    labels: tuple[str, ...]
    expiry: str  # skip | roll, for the day before and the day of weekly expiry

    @property
    def name(self) -> str:
        kind = {"condor": "Iron condor", "bull_put": "Bull put", "bear_call": "Bear call"}[
            self.family
        ]
        tail = "skipping expiry eve" if self.expiry == "skip" else "rolling past expiry eve"
        return f"{kind} OTM{self.short}/OTM{self.long} on {'+'.join(self.labels)} days, {tail}"

    @property
    def width_pts(self) -> int:
        return (self.long - self.short) * STRIKE_STEP

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "short": self.short,
            "long": self.long,
            "labels": list(self.labels),
            "expiry": self.expiry,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Spec:
        if not isinstance(raw, dict):
            raise SpecError("The algo definition is missing.")
        family = raw.get("family")
        if family not in FAMILIES:
            raise SpecError("Pick an iron condor, a bull put spread or a bear call spread.")
        try:
            short, long = int(raw.get("short")), int(raw.get("long"))
        except (TypeError, ValueError):
            raise SpecError("Strike distances must be whole numbers.") from None
        if not (1 <= short < long <= 8):
            raise SpecError(
                "The bought strike must be further out than the sold strike, within 8 strikes."
            )
        labels = tuple(raw.get("labels") or ())
        if not labels or any(label not in VALID_LABELS for label in labels):
            raise SpecError("Pick at least one kind of market day to trade.")
        expiry = raw.get("expiry", "skip")
        if expiry not in EXPIRY_HANDLING:
            raise SpecError("Expiry handling must be skip or roll.")
        return cls(family, short, long, labels, expiry)


def space(
    families: Iterable[str] = FAMILIES, label_sets: Iterable[tuple[str, ...]] = LABEL_SETS
) -> list[Spec]:
    """Every configuration the search will try, capped so the selection effect stays small."""
    out = [
        Spec(family, short, long, tuple(labels), expiry)
        for family in families
        for short, long in SHAPES
        for labels in label_sets
        for expiry in EXPIRY_HANDLING
    ]
    if len(out) > MAX_TRIALS:
        raise SpecError(
            f"That is {len(out)} configurations; at most {MAX_TRIALS} are searched at once."
        )
    return out


def _gate(spec: Spec, regime: RegimeResult, dte: int | None) -> str | None:
    """Why this spec stands aside today, or None. The one rule set shared by the Lab and live."""
    if regime.label not in spec.labels or regime.confidence < MIN_CONFIDENCE:
        return "regime"
    if dte is not None and dte <= 1 and spec.expiry == "skip":
        return "expiry eve"
    return None


def _config(spec: Spec, lots: int, dte: int | None, name: str) -> tuple[dict[str, Any], str]:
    expiry = "next_week" if dte is not None and dte <= 1 else "weekly"
    short, long = f"OTM{spec.short}", f"OTM{spec.long}"
    if spec.family == "condor":
        return condor_config(
            name, lots, expiry, short_offset=short, long_offset=long
        ), "iron_condor"
    return spread_config(
        name, spec.family, lots, expiry, short_offset=short, long_offset=long
    ), spec.family


def lab_plan_fn(spec: Spec, algo_id: str = "calm_condor") -> Callable[..., Plan]:
    """The plan function the Lab replays: one lot, same gates as ``live_plan``."""

    def plan_fn(regime, inputs, dte, extra):
        reason = _gate(spec, regime, dte)
        if reason:
            return Plan(algo_id, "skip", reason, None, 0, None, None)
        config, side = _config(spec, 1, dte, "c")
        return Plan(algo_id, "trade", "", config, 1, 0.0, side)

    return plan_fn


def live_plan(
    spec: Spec,
    algo_id: str,
    name: str,
    regime: RegimeResult,
    *,
    capital: float,
    lot_size: int,
    days_to_expiry: int | None,
    max_loss_pct: float = DEFAULT_MAX_LOSS_PCT,
) -> Plan:
    """The plan the daily runner acts on. Sized so the worst case fits the loss limit."""
    reason = _gate(spec, regime, days_to_expiry)
    if reason == "regime":
        return Plan(
            algo_id,
            "skip",
            f"{name} does not trade a {regime.label} market (or the data is too thin to say).",
            None,
            0,
            None,
            None,
        )
    if reason:
        return Plan(
            algo_id,
            "skip",
            f"Expiry is today or tomorrow, so {name} waits: next week's options earn too little "
            "time decay for one night.",
            None,
            0,
            None,
            None,
        )
    loss_per_lot = spec.width_pts * lot_size
    lots = min(int((capital * max_loss_pct / 100.0) // loss_per_lot), MAX_ENGINE_LOTS)
    if lots < 1:
        need = loss_per_lot * 100.0 / max_loss_pct
        return Plan(
            algo_id,
            "skip",
            f"Capital is too small for one lot with a {max_loss_pct:.0f} percent loss limit. "
            f"{name} needs about {need:,.0f} rupees.",
            None,
            0,
            None,
            None,
        )
    config, side = _config(spec, lots, days_to_expiry, f"{name} - {spec.family.replace('_', ' ')}")
    max_loss = float(lots * loss_per_lot)
    config["daily_loss_limit_inr"] = max_loss
    return Plan(
        algo_id,
        "trade",
        f"{regime.label.capitalize()} market: {side.replace('_', ' ')}.",
        config,
        lots,
        max_loss,
        side,
    )


# -- the search ---------------------------------------------------------------


def score(trades: list[dict[str, Any]]) -> float | None:
    """Net result less half the worst drawdown; None when there are too few trades to say."""
    stats = summarize([t["pnl"] for t in trades])
    if stats["trades"] < 1:
        return None
    return stats["total"] + DRAWDOWN_WEIGHT * stats["max_drawdown"]


def _segments(first: str, last: str) -> dict[str, tuple[str, str]]:
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    span = (b - a).days
    cut1 = a.fromordinal(a.toordinal() + int(span * TRAIN_SHARE))
    cut2 = a.fromordinal(a.toordinal() + int(span * (TRAIN_SHARE + VALIDATE_SHARE)))
    return {
        "train": (first, cut1.isoformat()),
        "validate": (cut1.isoformat(), cut2.isoformat()),
        "test": (cut2.isoformat(), last),
    }


def _within(trades: list[dict[str, Any]], lo: str, hi: str, *, first: bool) -> list[dict[str, Any]]:
    return [t for t in trades if (t["date"] >= lo if first else t["date"] > lo) and t["date"] <= hi]


def _pf(stats: dict[str, Any]) -> float:
    """Profit factor, with no losing trade at all (reported as None) counted as unbounded."""
    pf = stats["profit_factor"]
    return float("inf") if pf is None and (stats["total"] or 0) > 0 else (pf or 0.0)


def _verdict(winner: dict[str, Any], validate_ok: bool) -> dict[str, Any]:
    test, val = winner["test"], winner["validate"]
    reasons: list[str] = []
    if test["trades"] < MIN_EVAL_TRADES:
        reasons.append(
            f"Only {test['trades']} trades on the untouched period; at least {MIN_EVAL_TRADES} are needed."
        )
    if (test["total"] or 0) <= 0:
        reasons.append("It lost money on the period nothing was chosen on.")
    if _pf(test) < MIN_PROFIT_FACTOR:
        reasons.append(f"Its profit factor on that period is below {MIN_PROFIT_FACTOR}.")
    if not validate_ok or val["trades"] < MIN_EVAL_TRADES:
        reasons.append("It did not hold up on the validation period either.")
    if reasons:
        return {
            "edge_shown": False,
            "headline": "No edge shown. The best configuration found did not survive data it was not chosen on.",
            "reasons": reasons,
        }
    return {
        "edge_shown": True,
        "headline": "It held up on data it was not chosen on. That is one test period, not proof: run it in Sandbox.",
        "reasons": [],
    }


def search(
    specs: list[Spec],
    run: Callable[[Spec], list[dict[str, Any]]],
    *,
    baseline: Callable[[], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Run the walk-forward search. ``run`` replays one spec; ``baseline`` replays the algo to beat."""
    results = {spec: run(spec) for spec in specs}
    dates = sorted(t["date"] for trades in results.values() for t in trades)
    if not dates:
        raise SpecError("None of these configurations traded in the available history.")
    seg = _segments(dates[0], dates[-1])

    def cut(trades, name):
        lo, hi = seg[name]
        return _within(trades, lo, hi, first=name == "train")

    rows = []
    for spec, trades in results.items():
        train, validate, test = (cut(trades, n) for n in ("train", "validate", "test"))
        rows.append(
            {
                "spec": spec,
                "train": summarize([t["pnl"] for t in train]),
                "validate": summarize([t["pnl"] for t in validate]),
                "test": summarize([t["pnl"] for t in test]),
                "train_score": score(train),
                "validate_score": score(validate),
            }
        )

    eligible = [
        r for r in rows if r["train"]["trades"] >= MIN_TRAIN_TRADES and r["train_score"] is not None
    ]
    top = sorted(eligible, key=lambda r: r["train_score"], reverse=True)[:TOP_ON_TRAIN]
    base = None
    if baseline is not None:
        base_trades = baseline()
        base = summarize([t["pnl"] for t in cut(base_trades, "test")])
    out: dict[str, Any] = {
        "trials": len(specs),
        "segments": {k: list(v) for k, v in seg.items()},
        "lost_on_test": sum(
            1 for r in rows if (r["test"]["total"] or 0) < 0 and r["test"]["trades"] > 0
        ),
        "baseline_test": base,
    }
    if not top:
        out["winner"] = None
        out["verdict"] = {
            "edge_shown": False,
            "headline": "No configuration traded often enough on the training period to judge.",
            "reasons": [f"At least {MIN_TRAIN_TRADES} trades are needed on the training period."],
        }
        out["shortlist"] = []
        return out

    scored = [r for r in top if r["validate_score"] is not None]
    pool = scored or top
    winner = max(
        pool,
        key=lambda r: r["validate_score"] if r["validate_score"] is not None else float("-inf"),
    )
    validate_ok = (winner["validate"]["total"] or 0) > 0 and (
        _pf(winner["validate"])
    ) >= MIN_VALIDATE_PROFIT_FACTOR

    def public(r: dict[str, Any], *, with_test: bool) -> dict[str, Any]:
        item = {
            "spec": r["spec"].to_dict(),
            "name": r["spec"].name,
            "train": r["train"],
            "validate": r["validate"],
        }
        if with_test:
            item["test"] = r["test"]
        return item

    out["winner"] = public(winner, with_test=True)
    # The shortlist shows the other finalists' train and validate only: the test period
    # belongs to the winner alone, so a reader cannot pick a "better" one by peeking.
    out["shortlist"] = [public(r, with_test=False) for r in top if r is not winner]
    out["verdict"] = _verdict(winner, validate_ok)
    return out


def review(
    current: Spec, fresh: dict[str, Any], current_test: dict[str, Any] | None
) -> dict[str, Any] | None:
    """A proposal to switch, or None. Never applied here: a person decides.

    Proposed only when the new winner is a different configuration, shows an edge on
    data it was not chosen on, and the algo in use has done worse on that same period.
    """
    winner = fresh.get("winner")
    if not winner or not fresh["verdict"]["edge_shown"] or winner["spec"] == current.to_dict():
        return None
    mine = (current_test or {}).get("total")
    if mine is not None and mine >= (winner["test"]["total"] or 0):
        return None
    return {
        "spec": winner["spec"],
        "name": winner["name"],
        "why": f"On the latest untouched period it made Rs {winner['test']['total']:,.0f} per lot against "
        f"Rs {mine:,.0f} for the one you run."
        if mine is not None
        else "It shows an edge on data it was not chosen on.",
        "verdict": fresh["verdict"],
    }
