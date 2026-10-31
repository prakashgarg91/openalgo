"""Retail-realistic cost scenario: the arithmetic of one spread, and the dates that change it."""

import pandas as pd

from services.algos import costs


def spread(day="2025-06-02", exit_day=None, lot=75):
    return costs.realistic_cost(
        pd.Timestamp(day), pd.Timestamp(exit_day or day), 100.0, 10.0, 80.0, 5.0, lot
    )


def test_one_spread_adds_up_item_by_item():
    lot = 75
    turnover = (100 + 10 + 80 + 5) * lot  # 14,625
    brokerage = 80.0
    stt = (100 + 5) * lot * 0.001  # 7.875: the short at entry and the long at exit are sold
    exchange = turnover * 0.000345
    sebi = turnover * 0.000001
    gst = 0.18 * (brokerage + exchange + sebi)
    stamp = (10 + 80) * lot * 0.00003  # the long at entry and the short at exit are bought
    slippage = 4 * 0.15 * lot
    expected = brokerage + stt + exchange + sebi + gst + stamp + slippage
    assert abs(spread() - expected) < 1e-9
    assert (
        150 < spread() < 200
    )  # about Rs 170 a trade, against about Rs 270 in the conservative model


def test_the_stt_rate_follows_the_date_of_each_sale():
    before = spread("2026-03-30")
    after = spread("2026-04-02")
    assert after > before
    mixed = spread("2026-03-31", "2026-04-01")
    assert before < mixed < after


def test_the_lot_size_scales_the_money_but_not_the_order_charges():
    assert spread(lot=65) < spread(lot=75)
    assert spread(lot=65) > 80.0 * 1.18  # brokerage and its GST do not shrink with the lot
