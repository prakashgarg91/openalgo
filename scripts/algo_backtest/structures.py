"""Candidate structures for the algo research scripts.

A candidate is a condor or a bull put spread with a chosen shape, an optional
India VIX percentile filter, and a choice of skipping or rolling on expiry eve.
``plan_fn_for`` turns one into the plan function the Lab accepts.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos.templates import Plan, condor_config, spread_config  # noqa: E402

SHAPES = [(1, 3), (1, 4), (2, 4), (2, 5), (3, 5)]  # (short OTM, long OTM)


@dataclass(frozen=True)
class Cand:
    family: str  # condor | bullput
    short: int
    long: int
    vix_min: int | None
    expiry: str  # roll | skip

    @property
    def name(self) -> str:
        v = f"vix>={self.vix_min}" if self.vix_min else "any-vix"
        return f"{self.family} OTM{self.short}/OTM{self.long} {v} {self.expiry}"


def candidates():
    for short, long in SHAPES:
        for vix_min in (None, 50, 70):
            for expiry in ("roll", "skip"):
                yield Cand("condor", short, long, vix_min, expiry)
    for short, long in SHAPES:
        for vix_min in (None, 50):
            for expiry in ("roll", "skip"):
                yield Cand("bullput", short, long, vix_min, expiry)


def plan_fn_for(c: Cand):
    labels = ("calm",) if c.family == "condor" else ("calm", "trending")
    min_conf = 0.6 if c.family == "condor" else 0.5
    algo = "calm_condor" if c.family == "condor" else "zen"

    def skip(reason):
        return Plan(algo, "skip", reason, None, 0, None, None)

    def plan_fn(regime, inputs, dte, extra):
        if regime.label not in labels or regime.confidence < min_conf:
            return skip("regime")
        if c.vix_min and (extra["vix_rank"] is None or extra["vix_rank"] < c.vix_min):
            return skip("vix filter")
        if dte <= 1 and c.expiry == "skip":
            return skip("expiry eve")
        expiry = "next_week" if dte <= 1 else "weekly"
        if c.family == "condor":
            cfg = condor_config(
                "c", 1, expiry, short_offset=f"OTM{c.short}", long_offset=f"OTM{c.long}"
            )
            return Plan(algo, "trade", "", cfg, 1, 0.0, "iron_condor")
        cfg = spread_config(
            "c", "bull_put", 1, expiry, short_offset=f"OTM{c.short}", long_offset=f"OTM{c.long}"
        )
        return Plan(algo, "trade", "", cfg, 1, 0.0, "bull_put")

    return algo, plan_fn
