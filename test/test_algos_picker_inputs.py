"""The picker's input parsers: pure, with made-up broker responses."""

from datetime import UTC, date, datetime, timedelta, timezone

from services.algos import picker, picker_inputs

IST = timezone(timedelta(hours=5, minutes=30))


def test_minutes_since_the_open_follow_india_time():
    assert picker_inputs.minutes_since_open(datetime(2026, 11, 4, 9, 15, tzinfo=IST)) == 0
    assert picker_inputs.minutes_since_open(datetime(2026, 11, 4, 10, 18, tzinfo=IST)) == 63
    assert picker_inputs.minutes_since_open(datetime(2026, 11, 4, 4, 48, tzinfo=UTC)) == 63
    assert picker_inputs.minutes_since_open(datetime(2026, 11, 4, 8, 0, tzinfo=IST)) < 0


def test_expiry_text_parses_in_both_shapes_and_the_nearest_unpassed_one_wins():
    assert picker_inputs.parse_expiry("09NOV26") == date(2026, 11, 9)
    assert picker_inputs.parse_expiry("09-NOV-26") == date(2026, 11, 9)
    assert picker_inputs.parse_expiry("garbage") is None
    expiries = ["03-NOV-26", "09-NOV-26", "17-NOV-26"]
    assert picker_inputs.nearest_expiry(expiries, date(2026, 11, 4)) == "09NOV26"
    assert picker_inputs.nearest_expiry(expiries, date(2026, 11, 9)) == "09NOV26"
    assert picker_inputs.nearest_expiry(expiries, date(2026, 12, 1)) is None


def _response():
    row = lambda strike: {  # noqa: E731
        "strike": strike,
        "ce": {
            "symbol": f"NIFTY09NOV26{int(strike)}CE",
            "bid": 10,
            "ask": 11,
            "ltp": 10.5,
            "lotsize": 65,
        },
        "pe": {
            "symbol": f"NIFTY09NOV26{int(strike)}PE",
            "bid": 9,
            "ask": 10,
            "ltp": 9.5,
            "lotsize": 65,
        },
    }
    return {"chain": [row(23900.0), row(23950.0)], "underlying_ltp": 23928.3}


def test_the_chain_becomes_a_lookup_with_the_lot_size():
    chain, lot = picker_inputs.chain_map(_response())
    assert lot == 65
    assert chain[("CE", 23950.0)]["ask"] == 11 and chain[("PE", 23900.0)]["symbol"].endswith("PE")


def test_a_row_without_a_leg_is_skipped_not_invented():
    response = {
        "chain": [
            {
                "strike": 24000.0,
                "ce": None,
                "pe": {"symbol": "X", "bid": 1, "ask": 2, "lotsize": 65},
            }
        ]
    }
    chain, _ = picker_inputs.chain_map(response)
    assert ("CE", 24000.0) not in chain and ("PE", 24000.0) in chain


def test_the_margin_basket_has_one_position_per_leg_with_full_quantity():
    chain = {
        ("CE", 23950.0): {"bid": 10, "ask": 12, "symbol": "NIFTY09NOV2623950CE"},
        ("PE", 23950.0): {"bid": 9, "ask": 11, "symbol": "NIFTY09NOV2623950PE"},
    }
    tpl = picker.template("short_straddle")
    legs = picker.price_legs(tpl, 23950.0, 50, chain)
    positions = picker_inputs.margin_positions(tpl, legs, chain, 65)
    assert [p["action"] for p in positions] == ["SELL", "SELL"]
    assert all(p["quantity"] == "65" and p["product"] == "NRML" for p in positions)
    chain[("CE", 23950.0)].pop("symbol")
    assert picker_inputs.margin_positions(tpl, legs, chain, 65) is None


def test_momentum_is_the_move_since_the_open_and_missing_when_unknown():
    assert round(picker_inputs.momentum_pct({"ltp": 24000.0, "open": 23880.0}), 2) == 0.5
    assert picker_inputs.momentum_pct({"ltp": 24000.0}) is None
    assert picker_inputs.momentum_pct(None) is None
