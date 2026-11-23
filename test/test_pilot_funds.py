"""Tests for services/algos/pilot_funds.py: the report math and the read-only broker path.

Pure and monkeypatched tests. No network, no real database, no broker, no app; every external
call is replaced, and gather runs on a passed ``today`` so no wall clock is read.
"""

from __future__ import annotations

from datetime import date

import services.algos.pilot_funds as pf
from services.algos import atm200_rule as rule
from services.algos import sandbox_bot as sb

TODAY = date(2026, 11, 23)  # a Monday; the 19-Nov weekly has already gone
EXPIRY_TEXT = "26-Nov-26"
EXPIRY = date(2026, 11, 26)
SPOT = 25010.0  # atm_strike -> 25000, so the bought call sits at 25200
PREMIUM_EACH = 4127.0 / 65
SOLD = sb.contract_symbol(EXPIRY, 25000)
LONG = sb.contract_symbol(EXPIRY, 25200)


def _quotes_ok(symbol, exchange, api_key=None, auth_token=None, feed_token=None, broker=None):
    ltp = SPOT if symbol == "NIFTY" else PREMIUM_EACH
    return True, {"status": "success", "data": {"ltp": ltp}}, 200


def _expiries_ok(exchange, underlying, instrumenttype):
    return ["19-Nov-26", EXPIRY_TEXT, "03-Dec-26"]


def _funds_ok(api_key=None, auth_token=None, broker=None):
    return True, {"status": "success", "data": {"availablecash": "32041.00"}}, 200


def test_report_matches_the_measured_spread():
    """The 18 Nov measurement: total 49,898 with the 4,127 premium inside, against 32,041 cash."""
    report = pf.funds_report(
        sold_symbol=SOLD,
        long_symbol=LONG,
        quantity=65,
        spot=SPOT,
        margin_total=49898.0,
        premium_each=PREMIUM_EACH,
        available_cash=32041.0,
    )
    assert report == {
        "sold_symbol": SOLD,
        "long_symbol": LONG,
        "quantity": 65,
        "spot": 25010.0,
        "margin_total": 49898.0,
        "premium": 4127.0,
        "margin_excl_premium": 45771.0,
        "buffer": 4577.1,
        "needed": 54475.1,
        "available_cash": 32041.0,
        "short_by": 22434.1,
        "enough": False,
    }


def test_report_is_enough_when_cash_covers_the_need():
    report = pf.funds_report(
        sold_symbol=SOLD,
        long_symbol=LONG,
        quantity=65,
        spot=SPOT,
        margin_total=49898.0,
        premium_each=PREMIUM_EACH,
        available_cash=60000.0,
    )
    assert report["needed"] == 54475.1
    assert report["short_by"] == 0.0
    assert report["enough"] is True


def test_gather_reads_the_broker_internally_and_builds_today_spread(monkeypatch):
    calls = {}

    def quotes(symbol, exchange, api_key=None, auth_token=None, feed_token=None, broker=None):
        calls.setdefault("quotes", []).append((symbol, exchange, auth_token, broker, api_key))
        return _quotes_ok(symbol, exchange, api_key=api_key, auth_token=auth_token, broker=broker)

    def expiries(exchange, underlying, instrumenttype):
        calls["expiries"] = (exchange, underlying, instrumenttype)
        return _expiries_ok(exchange, underlying, instrumenttype)

    def margin(margin_data, api_key=None, auth_token=None, broker=None):
        calls["margin"] = (margin_data, auth_token, broker, api_key)
        return (
            True,
            {
                "status": "success",
                "data": {"total_margin_required": 215226.83, "final_margin": 45771.0},
            },
            200,
        )

    def funds(api_key=None, auth_token=None, broker=None):
        calls["funds"] = (auth_token, broker, api_key)
        return _funds_ok(api_key=api_key, auth_token=auth_token, broker=broker)

    monkeypatch.setattr(pf, "get_quotes", quotes)
    monkeypatch.setattr(pf, "get_distinct_expiries", expiries)
    monkeypatch.setattr(pf, "calculate_margin", margin)
    monkeypatch.setattr(pf, "get_funds", funds)

    result = pf.gather("token-1", "upstox", today=TODAY)

    assert result["ok"] is True
    assert result["expiry"] == "2026-11-26"
    assert result["as_of"]
    assert result["report"]["sold_symbol"] == SOLD
    assert result["report"]["long_symbol"] == LONG
    assert result["report"]["quantity"] == rule.LOT == 65
    assert result["report"]["short_by"] == 22434.1
    assert result["report"]["enough"] is False

    # every read went out as an internal call: auth_token and broker, never an api_key
    assert calls["expiries"] == ("NFO", "NIFTY", "options")
    for _symbol, _exchange, token, broker, api_key in calls["quotes"]:
        assert token == "token-1" and broker == "upstox" and api_key is None
    assert calls["quotes"][0][:2] == ("NIFTY", "NSE_INDEX")
    assert calls["quotes"][1][:2] == (LONG, "NFO")
    margin_data, token, broker, api_key = calls["margin"]
    assert token == "token-1" and broker == "upstox" and api_key is None
    assert margin_data["positions"] == [
        {
            "symbol": SOLD,
            "exchange": "NFO",
            "action": "SELL",
            "quantity": "65",
            "product": "NRML",
            "pricetype": "MARKET",
            "price": "0",
            "trigger_price": "0",
        },
        {
            "symbol": LONG,
            "exchange": "NFO",
            "action": "BUY",
            "quantity": "65",
            "product": "NRML",
            "pricetype": "MARKET",
            "price": "0",
            "trigger_price": "0",
        },
    ]
    token, broker, api_key = calls["funds"]
    assert token == "token-1" and broker == "upstox" and api_key is None


def test_gather_turns_a_margin_refusal_into_one_plain_sentence(monkeypatch):
    def refused(margin_data, api_key=None, auth_token=None, broker=None):
        return False, {"status": "error", "message": "Upstox API Error: Authentication"}, 403

    def unreachable_funds(**kwargs):
        raise AssertionError("funds must not be read once the margin has failed")

    monkeypatch.setattr(pf, "get_quotes", _quotes_ok)
    monkeypatch.setattr(pf, "get_distinct_expiries", _expiries_ok)
    monkeypatch.setattr(pf, "calculate_margin", refused)
    monkeypatch.setattr(pf, "get_funds", unreachable_funds)

    result = pf.gather("token-1", "upstox", today=TODAY)

    assert result == {
        "ok": False,
        "message": "Could not read the margin from Upstox. Sign in to Upstox and try again.",
    }


def test_on_an_expiry_day_the_next_weekly_is_sized_not_the_one_expiring_today(monkeypatch):
    """The bot never enters on the expiry day itself, so the check must not size today's contract."""
    monkeypatch.setattr(pf, "get_distinct_expiries", lambda *a: ["23-Nov-26", "30-Nov-26"])
    assert pf._expiry_or_stop(date(2026, 11, 23), "Upstox") == "30-Nov-26"
    assert pf._expiry_or_stop(date(2026, 11, 20), "Upstox") == "23-Nov-26"


def test_the_unhedged_total_alone_is_refused_not_shown(monkeypatch):
    """Without the after-benefit figure the check refuses: the unhedged total overstates about five times."""
    monkeypatch.setattr(
        pf,
        "calculate_margin",
        lambda *a, **k: (
            True,
            {"status": "success", "data": {"total_margin_required": 215226.83}},
            200,
        ),
    )
    try:
        pf._margin_or_stop("A", "B", "token-1", "upstox", "Upstox")
    except pf._ReadError as why:
        assert "margin" in why.message
    else:
        raise AssertionError("the unhedged total was accepted")
