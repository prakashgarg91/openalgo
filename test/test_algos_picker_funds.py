"""Capital and after-close price handling for the strategy picker."""

import pytest
from test_algos_picker import SPOT, STEP, conditions, make_chain

from services.algos import picker, picker_inputs


def _chain_with_symbols():
    chain = make_chain()
    for (kind, strike), quote in chain.items():
        quote["symbol"] = f"NIFTY{int(strike)}{kind}"
    return chain


def test_final_margin_includes_the_bought_leg_premium(monkeypatch):
    chain = _chain_with_symbols()
    buy_quote = chain[("PE", SPOT - 4 * STEP)]
    buy_quote.update(bid=192.4, ask=192.4)

    monkeypatch.setattr(
        "services.margin_service.calculate_margin",
        lambda *_args, **_kwargs: (
            True,
            {"data": {"total_margin_required": 215227, "final_margin": 40675}},
            None,
        ),
    )
    margins = picker_inputs.fetch_margins("key", chain, conditions(), only={"bull_put_spread"})

    assert margins["bull_put_spread"] == pytest.approx(40675 + 192.4 * 65)


def test_total_margin_without_final_margin_is_not_stored(monkeypatch):
    monkeypatch.setattr(
        "services.margin_service.calculate_margin",
        lambda *_args, **_kwargs: (True, {"data": {"total_margin_required": 215227}}, None),
    )
    margins = picker_inputs.fetch_margins(
        "key", _chain_with_symbols(), conditions(), only={"bull_put_spread"}
    )
    assert "bull_put_spread" not in margins


def test_last_price_mode_uses_ltp_for_both_sides_and_rejects_missing_ltp():
    chain = make_chain()
    quote = chain[("CE", SPOT)]
    legs = picker.price_legs(picker.template("long_call"), SPOT, STEP, chain, use_last_price=True)
    assert legs[0].bid == legs[0].ask == quote["ltp"]

    quote.pop("ltp")
    assert (
        picker.price_legs(picker.template("long_call"), SPOT, STEP, chain, use_last_price=True)
        is None
    )


def test_regular_mode_still_rejects_a_stale_one_sided_quote():
    chain = make_chain()
    chain[("CE", SPOT)].update(bid=0.05, ask=0)
    assert picker.price_legs(picker.template("long_call"), SPOT, STEP, chain) is None


def test_after_close_ranking_uses_last_prices_and_shows_the_indicative_note():
    chain = make_chain()
    chain[("CE", SPOT)].update(bid=0.05, ask=0.60, ltp=17.25)
    result = picker.rank(
        conditions(minutes_since_open=500), chain, picker.Mandate(100_000, 100_000)
    )
    long_call = next(
        row for row in result["ranked"] + result["blocked"] if row["id"] == "long_call"
    )

    assert long_call["priced_legs"][0]["price"] == 17.25
    assert result["header"]["notes"][0] == (
        "The market is closed, so prices are the last traded ones: indicative only, not what an order would get now. The time score is zero."
    )
