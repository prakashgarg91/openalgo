"""Sandbox round trips: dated by entry, net of charges, first in first out."""

from services.algos import sandbox_round_trips as rt


def fill(symbol, action, qty, price, ts):
    return {"symbol": symbol, "action": action, "quantity": qty, "price": price, "timestamp": ts}


def test_the_zen_spread_of_13_to_17_november_is_dated_by_its_entry_and_matches_the_dashboard_gross():
    fills = [
        fill("P25050", "SELL", 65, 99.10, "2026-11-13 15:05:03"),
        fill("P24900", "BUY", 65, 51.40, "2026-11-13 15:05:03"),
        fill("P25050", "BUY", 65, 9.95, "2026-11-17 09:15:14"),
        fill("P24900", "SELL", 65, 1.55, "2026-11-17 09:45:08"),
    ]
    out = rt.round_trips(fills)
    assert out["open"] == [] and len(out["trips"]) == 2
    assert {t["entry_date"] for t in out["trips"]} == {"2026-11-13"}
    gross = sum(t["gross"] for t in out["trips"])
    assert gross == 2554.50  # the figure the dashboard showed
    day = rt.by_entry_date(out["trips"])
    assert [d["entry_date"] for d in day] == ["2026-11-13"]
    assert day[0]["net_after_charges"] < 2554.50
    assert 80 < day[0]["charges"] < 200  # four fills, Rs 20 brokerage each plus taxes
    assert day[0]["net_after_charges_and_slippage"] < day[0]["net_after_charges"]


def test_a_partial_close_is_matched_first_in_first_out_and_charged_once_in_total():
    fills = [
        fill("X", "BUY", 100, 10.0, "2026-11-02 10:00:00"),
        fill("X", "SELL", 60, 12.0, "2026-11-03 10:00:00"),
        fill("X", "SELL", 40, 11.0, "2026-11-04 10:00:00"),
    ]
    trips = rt.round_trips(fills)["trips"]
    assert [t["quantity"] for t in trips] == [60, 40]
    assert [t["gross"] for t in trips] == [120.0, 40.0]
    opening = rt.fill_charges("BUY", 100, 10.0, "2026-11-02")
    split = sum(rt.fill_charges("BUY", t["quantity"], 10.0, "2026-11-02") for t in trips)
    assert split > opening  # charging each piece in full would have been wrong (two brokerages)
    # the opening fill's charges are split by quantity, so they add up to ONE fill's charges
    paid = sum(t["charges"] for t in trips)
    exits = rt.fill_charges("SELL", 60, 12.0, "2026-11-03") + rt.fill_charges(
        "SELL", 40, 11.0, "2026-11-04"
    )
    assert abs(paid - (opening + exits)) < 0.05


def test_an_unmatched_opening_fill_is_reported_open_not_as_a_result():
    out = rt.round_trips([fill("Y", "SELL", 65, 50.0, "2026-11-17 10:00:00")])
    assert out["trips"] == [] and out["open"][0]["symbol"] == "Y"


def test_stt_applies_only_to_sells_and_rises_from_the_first_of_april_2026():
    before = rt.fill_charges("SELL", 100, 100.0, "2026-03-31")
    after = rt.fill_charges("SELL", 100, 100.0, "2026-04-01")
    buy = rt.fill_charges("BUY", 100, 100.0, "2026-04-01")
    assert after - before > 4.9  # 10,000 turnover at 0.05 percent more STT
    assert after > buy
