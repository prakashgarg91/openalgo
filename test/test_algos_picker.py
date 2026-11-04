"""The strategy picker ranks structures by how well today's conditions suit their design.

It never forecasts profit, never chooses for the trader and never promotes anything. These tests pin the
numbers (payoff, costs), the hard blocks (unbounded loss, daily cap) and the honesty guards.
"""

import math

import pytest

from services.algos import picker
from services.algos.mandate import ONE_LAKH

STEP = 50
SPOT = 23950.0


def make_chain(spot=SPOT, step=STEP, half_spread=0.5):
    """A toy chain: intrinsic plus a time value that shrinks away from the money."""
    chain = {}
    for i in range(-12, 13):
        strike = spot + i * step
        time_value = max(2.0, 150.0 * math.exp(-abs(i) / 2.5))
        ce = max(spot - strike, 0.0) + time_value
        pe = max(strike - spot, 0.0) + time_value
        for kind, mid in (("CE", ce), ("PE", pe)):
            chain[(kind, strike)] = {
                "bid": round(mid - half_spread, 2),
                "ask": round(mid + half_spread, 2),
                "ltp": mid,
                "oi": 100000,
                "volume": 50000,
            }
    return chain


def conditions(**kw):
    base = dict(
        bias="neutral",
        bias_score=0.0,
        regime_label="calm",
        regime_confidence=1.0,
        vix=15.0,
        vix_change_pct=0.0,
        minutes_since_open=60,
        dte=5,
        spot=SPOT,
        step=STEP,
        lot=65,
        momentum_pct=0.0,
    )
    base.update(kw)
    return picker.Conditions(**base)


def by_id(result, template_id):
    for row in result["ranked"] + result["blocked"]:
        if row["id"] == template_id:
            return row
    raise AssertionError(template_id)


def test_there_are_at_least_twenty_templates_with_unique_ids():
    ids = [t.id for t in picker.TEMPLATES]
    assert len(ids) >= 20 and len(ids) == len(set(ids))


def test_a_long_call_loses_exactly_its_premium_and_is_unbounded_upward():
    legs = picker.price_legs(picker.template("long_call"), SPOT, STEP, make_chain())
    stats = picker.payoff_stats(legs, 65)
    premium = legs[0].price * 65
    assert stats["max_loss"] == pytest.approx(premium)
    assert stats["unbounded_loss"] is False
    assert stats["max_profit"] is None  # unbounded profit


def test_a_short_straddle_has_unbounded_loss():
    legs = picker.price_legs(picker.template("short_straddle"), SPOT, STEP, make_chain())
    assert picker.payoff_stats(legs, 65)["unbounded_loss"] is True


def test_a_bull_call_spread_loses_its_debit_and_gains_width_minus_debit():
    legs = picker.price_legs(picker.template("bull_call_spread"), SPOT, STEP, make_chain())
    stats = picker.payoff_stats(legs, 65)
    debit_pts = legs[0].price - legs[1].price
    assert stats["max_loss"] == pytest.approx(debit_pts * 65)
    assert stats["max_profit"] == pytest.approx((150 - debit_pts) * 65)  # 3 strikes of 50 points
    assert len(stats["breakevens"]) == 1


def test_a_short_iron_condor_is_defined_risk_with_two_breakevens():
    legs = picker.price_legs(picker.template("short_iron_condor"), SPOT, STEP, make_chain())
    stats = picker.payoff_stats(legs, 65)
    assert stats["unbounded_loss"] is False and len(stats["breakevens"]) == 2
    assert stats["net_credit"] > 0


def test_a_leg_with_no_quote_leaves_the_structure_unpriced():
    chain = make_chain()
    chain[("CE", SPOT)]["bid"] = 0
    assert picker.price_legs(picker.template("long_call"), SPOT, STEP, chain) is None


def test_unbounded_loss_and_a_loss_above_the_daily_cap_are_blocked_not_hidden():
    result = picker.rank(conditions(), make_chain(), ONE_LAKH)
    short_straddle = by_id(result, "short_straddle")
    assert short_straddle in result["blocked"]
    assert any("unlimited" in r.lower() for r in short_straddle["blocked_because"])
    # a wide bought strangle at 1 lot fits; a cap of Rs 500 blocks almost everything
    tiny = picker.rank(
        conditions(), make_chain(), picker.Mandate(capital=100_000.0, max_daily_loss=500.0)
    )
    assert len(tiny["blocked"]) > len(result["blocked"])
    assert all(
        any("cap" in r.lower() or "unlimited" in r.lower() for r in row["blocked_because"])
        for row in tiny["blocked"]
        if row["priced"]
    )


def test_a_bullish_day_ranks_bull_structures_above_bear_structures():
    result = picker.rank(
        conditions(bias="bullish", bias_score=0.8, momentum_pct=0.5), make_chain(), ONE_LAKH
    )
    ranks = {row["id"]: i for i, row in enumerate(result["ranked"])}
    assert ranks["bull_call_spread"] < ranks["bear_put_spread"]
    assert ranks["bull_put_spread"] < ranks["bear_call_spread"]


def test_a_volatile_day_favours_buying_premium_and_a_calm_one_selling_it():
    volatile = picker.rank(
        conditions(regime_label="volatile", vix=22.0, vix_change_pct=9.0), make_chain(), ONE_LAKH
    )
    calm = picker.rank(
        conditions(regime_label="calm", vix=22.0, vix_change_pct=-4.0), make_chain(), ONE_LAKH
    )
    assert by_id(volatile, "long_straddle")["score"] > by_id(calm, "long_straddle")["score"]
    assert by_id(calm, "short_iron_condor")["score"] > by_id(volatile, "short_iron_condor")["score"]


def test_the_first_minutes_and_a_closed_market_score_low_on_time():
    open_ = picker.rank(conditions(minutes_since_open=60), make_chain(), ONE_LAKH)
    early = picker.rank(conditions(minutes_since_open=2), make_chain(), ONE_LAKH)
    closed = picker.rank(conditions(minutes_since_open=-30), make_chain(), ONE_LAKH)
    assert (
        by_id(early, "bull_call_spread")["components"]["time"]
        < by_id(open_, "bull_call_spread")["components"]["time"]
    )
    assert by_id(closed, "bull_call_spread")["components"]["time"] == 0.0
    assert "closed" in closed["header"]["notes"][0].lower()


def test_a_wide_spread_lowers_the_liquidity_score_and_raises_the_cost():
    tight = picker.rank(conditions(), make_chain(half_spread=0.5), ONE_LAKH)
    wide = picker.rank(conditions(), make_chain(half_spread=5.0), ONE_LAKH)
    t, w = by_id(tight, "long_straddle"), by_id(wide, "long_straddle")
    assert w["components"]["liquidity"] < t["components"]["liquidity"]
    assert w["costs"]["spread"] > t["costs"]["spread"]


def test_the_charges_follow_the_realistic_cost_model_for_one_round_trip():
    legs = picker.price_legs(picker.template("long_call"), SPOT, STEP, make_chain())
    c = picker.round_trip_costs(legs, 65)
    price = legs[0].price
    brokerage = 2 * 20.0
    exchange = 2 * price * 65 * 0.000345
    assert c["charges"] > brokerage + exchange  # plus STT on the exit sale, GST, stamp
    assert c["spread"] == pytest.approx((legs[0].ask - legs[0].bid) * 65)


def test_missing_inputs_lower_confidence_and_are_named():
    result = picker.rank(
        conditions(vix=None, vix_change_pct=None, regime_confidence=0.4), make_chain(), ONE_LAKH
    )
    header = result["header"]
    assert header["confidence"] < 0.5
    assert any("India VIX" in n for n in header["notes"])


def test_every_row_carries_its_evidence_status_and_the_header_says_it_is_not_a_forecast():
    result = picker.rank(conditions(), make_chain(), ONE_LAKH)
    assert all(row["evidence"] for row in result["ranked"] + result["blocked"])
    assert "not a forecast" in result["header"]["disclaimer"].lower()
    assert "forward test" in by_id(result, "bear_call_spread")["evidence"].lower()
    assert "no edge" in by_id(result, "short_iron_condor")["evidence"].lower()


def test_the_result_never_names_a_pick():
    result = picker.rank(conditions(), make_chain(), ONE_LAKH)
    assert "pick" not in result and "recommended" not in result


def test_the_words_a_trader_reads_avoid_the_banned_ones():
    result = picker.rank(conditions(), make_chain(), ONE_LAKH)
    text = repr(result).lower()
    assert "arm" not in {w.strip(".,;:()'\"") for w in text.split()}
    assert "paper trading" not in text


def test_capital_comes_from_the_broker_margin_when_given_and_blocks_above_capital():
    result = picker.rank(
        conditions(),
        make_chain(),
        ONE_LAKH,
        margins={"short_iron_condor": 40_000.0, "bull_put_spread": 150_000.0},
    )
    condor = by_id(result, "short_iron_condor")
    assert condor["capital_required"] == 40_000.0 and condor["capital_source"] == "broker"
    over = by_id(result, "bull_put_spread")
    assert over in result["blocked"]
    assert any("more than your capital" in r for r in over["blocked_because"])


def test_a_bought_structure_needs_its_premium_as_capital_without_a_broker_margin():
    row = by_id(picker.rank(conditions(), make_chain(), ONE_LAKH), "long_call")
    assert row["capital_source"] == "premium paid"
    assert row["capital_required"] == pytest.approx(-row["stats"]["net_credit"])


def test_the_header_carries_the_typical_move_from_india_vix():
    header = picker.rank(conditions(vix=16.0), make_chain(), ONE_LAKH)["header"]
    assert (
        40 < header["expected_move"]["fifteen_minutes"] < 60
    )  # 23,950 at 16 percent is about 49 points
    assert header["expected_move"]["day"] > header["expected_move"]["fifteen_minutes"]
