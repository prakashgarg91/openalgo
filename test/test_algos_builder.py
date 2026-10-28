"""The builder's search must not fool itself, and a built algo must trade what the Lab tested."""

import random
from datetime import date, timedelta

import pytest

from services.algos import builder as b
from services.algos.context import RegimeResult

DAYS = []
_d = date(2018, 1, 1)
while _d < date(2024, 1, 1):
    if _d.weekday() < 5:
        DAYS.append(_d.isoformat())
    _d += timedelta(1)


def regime(label="calm", confidence=1.0):
    return RegimeResult(label, "neutral", 0.0, confidence, ("ok",), ())


def world(mean, seed, n=60):
    rng = random.Random(seed)
    specs = b.space()[:n]
    return specs, {
        s: [{"date": x, "pnl": rng.gauss(mean, 800)} for x in DAYS if rng.random() < 0.45]
        for s in specs
    }


def test_space_is_bounded_and_counted():
    assert len(b.space()) == 60
    with pytest.raises(b.SpecError):
        b.space(label_sets=[("calm",), ("calm", "trending"), ("trending",), ("volatile",)])


def test_spec_round_trip_and_refusals():
    spec = b.Spec("condor", 2, 5, ("calm",), "skip")
    assert b.Spec.from_dict(spec.to_dict()) == spec
    for bad in (
        None,
        {"family": "naked_put", "short": 1, "long": 3, "labels": ["calm"]},
        {"family": "condor", "short": 3, "long": 3, "labels": ["calm"]},
        {"family": "condor", "short": 1, "long": 9, "labels": ["calm"]},
        {"family": "condor", "short": 1, "long": 3, "labels": []},
        {"family": "condor", "short": 1, "long": 3, "labels": ["moonless"]},
        {"family": "condor", "short": "x", "long": 3, "labels": ["calm"]},
    ):
        with pytest.raises(b.SpecError):
            b.Spec.from_dict(bad)


def test_overfit_winner_on_train_is_not_blessed():
    """A configuration that won big in training and then lost must not be reported as an edge."""
    specs, data = world(-40, seed=1, n=10)
    lucky = specs[0]
    data[lucky] = [
        {"date": x, "pnl": 600.0 if x < "2021-01-01" else -700.0}
        for x in DAYS
        if x.endswith(("1", "3", "5"))
    ]
    result = b.search(specs, lambda s: data[s])
    assert not result["verdict"]["edge_shown"]
    assert result["trials"] == 10
    if result["winner"]["spec"] == lucky.to_dict():
        assert result["winner"]["test"]["total"] < 0


def test_a_real_edge_is_found_and_stated_with_a_caveat():
    specs, data = world(250, seed=3)
    result = b.search(specs, lambda s: data[s])
    assert result["verdict"]["edge_shown"]
    assert "not proof" in result["verdict"]["headline"]


def test_pure_noise_rarely_passes():
    hits = sum(
        b.search(*(lambda w: (w[0], lambda s, d=w[1]: d[s]))(world(0, seed)))["verdict"][
            "edge_shown"
        ]
        for seed in range(60)
    )
    assert hits <= 6  # measured 6 of 150 (4%) for the same rule


def test_test_period_belongs_to_the_winner_alone():
    specs, data = world(100, seed=5)
    result = b.search(specs, lambda s: data[s])
    assert "test" in result["winner"]
    assert all("test" not in item for item in result["shortlist"])


def test_segments_are_ordered_and_disjoint():
    specs, data = world(0, seed=7, n=8)
    seg = b.search(specs, lambda s: data[s])["segments"]
    assert seg["train"][1] == seg["validate"][0] and seg["validate"][1] == seg["test"][0]
    assert seg["train"][0] < seg["train"][1] < seg["validate"][1] < seg["test"][1]


def test_nothing_traded_is_reported_plainly():
    with pytest.raises(b.SpecError):
        b.search(b.space()[:2], lambda s: [])


def test_review_proposes_only_a_better_proven_change():
    specs, data = world(250, seed=3)
    fresh = b.search(specs, lambda s: data[s])
    other = next(c for c in specs if c.to_dict() != fresh["winner"]["spec"])
    proposal = b.review(other, fresh, {"total": -5000.0})
    assert proposal and proposal["spec"] == fresh["winner"]["spec"]
    assert b.review(other, fresh, {"total": 10**9}) is None  # the one in use is already better
    same = b.Spec.from_dict(fresh["winner"]["spec"])
    assert b.review(same, fresh, {"total": -5000.0}) is None  # nothing to change
    weak = b.search(*(lambda w: (w[0], lambda s, d=w[1]: d[s]))(world(-50, 2)))
    assert b.review(other, weak, {"total": -5000.0}) is None  # no edge shown, no proposal


def _legs(plan):
    return sorted((x["position"], x["option_type"], x["atm_offset"]) for x in plan.config["legs"])


@pytest.mark.parametrize("family", b.FAMILIES)
@pytest.mark.parametrize("dte", [0, 1, 2, 4])
@pytest.mark.parametrize("label", ["calm", "trending", "volatile"])
@pytest.mark.parametrize("expiry", b.EXPIRY_HANDLING)
def test_live_plan_trades_exactly_when_the_lab_plan_does(family, dte, label, expiry):
    spec = b.Spec(family, 2, 5, ("calm",), expiry)
    r = regime(label)
    lab = b.lab_plan_fn(spec)(r, None, dte, {})
    live = b.live_plan(
        spec, "custom_1", "Mine", r, capital=500_000, lot_size=75, days_to_expiry=dte
    )
    assert lab.action == live.action
    if lab.action == "trade":
        assert _legs(lab) == _legs(live)


def test_live_plan_sizes_to_the_loss_limit_and_refuses_thin_capital():
    spec = b.Spec("bull_put", 2, 5, ("calm",), "skip")  # 150 points wide
    plan = b.live_plan(
        spec, "custom_1", "Mine", regime(), capital=500_000, lot_size=75, days_to_expiry=4
    )
    assert plan.lots == 4 and plan.max_loss_inr == 4 * 150 * 75
    thin = b.live_plan(
        spec, "custom_1", "Mine", regime(), capital=20_000, lot_size=75, days_to_expiry=4
    )
    assert thin.action == "skip" and "Capital is too small" in thin.reason


def test_low_confidence_stands_aside_in_words_a_trader_can_use():
    spec = b.Spec("condor", 2, 5, ("calm",), "skip")
    plan = b.live_plan(
        spec,
        "custom_1",
        "Mine",
        regime(confidence=0.2),
        capital=500_000,
        lot_size=75,
        days_to_expiry=4,
    )
    assert plan.action == "skip" and "data is too thin" in plan.reason
