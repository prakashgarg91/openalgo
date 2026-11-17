"""Tests for services/algos/portfolio_report.py. Pure functions, no network."""

from __future__ import annotations

import math

from services.algos.portfolio_report import (
    DAILY_CAP_RUPEES,
    NO_TRADE,
    hindsight_days,
    hindsight_picks,
    portfolio_days,
    summarise,
    verdict,
)


def _trade(date: str, algo: str, cell: str, net: float) -> dict:
    return {"date": date, "algo": algo, "cell": cell, "net": net}


# Worked example used by several tests.
#   Jan picks: c1 -> A, c2 -> A.   Feb picks: c1 -> B, c2 -> no_trade.
#   Chosen trades: 01-05 A c1 +5000, 01-06 A c2 -30000, 02-03 B c1 +4000.
#   Unchosen rows: 01-05 B c1 -3000, 02-04 A c1 +1000 (Feb c1 is B), 02-05 B c2 (no_trade).
EXAMPLE_TRADES = [
    _trade("2026-01-05", "A", "c1", 5000.0),
    _trade("2026-01-05", "B", "c1", -3000.0),
    _trade("2026-01-06", "A", "c2", -30000.0),
    _trade("2026-02-03", "B", "c1", 4000.0),
    _trade("2026-02-04", "A", "c1", 1000.0),
    _trade("2026-02-05", "B", "c2", 9000.0),
]
EXAMPLE_PICKS = {
    "2026-01": {"c1": "A", "c2": "A"},
    "2026-02": {"c1": "B", "c2": NO_TRADE},
}

# Ten flat-ish days, all positive: mean 1000, sample sd sqrt(280000/9), t about 17.9.
PASSING_DAYS = [
    (f"2026-01-{day:02d}", net)
    for day, net in enumerate([1000, 1200, 800, 1100, 900, 1000, 1300, 700, 1000, 1000], start=1)
]


def _passing_summary() -> dict:
    return {
        "n_trades_days": 10,
        "net_total": 10000.0,
        "mean_per_trading_day": 1000.0,
        "sd": 176.0,
        "t_stat": 5.0,
        "worst_day": 700.0,
        "days_over_cap": 0,
        "max_drawdown": 0.0,
        "positive_halves": True,
        "months_negative": 0,
    }


def test_portfolio_days_worked_example():
    days = portfolio_days(EXAMPLE_TRADES, EXAMPLE_PICKS)
    assert days == [
        ("2026-01-05", 5000.0),
        ("2026-01-06", -30000.0),
        ("2026-02-03", 4000.0),
    ]


def test_summarise_worked_example():
    # Nets 5000, -30000, 4000 (in date order).
    # net_total = -21000; mean = -7000.
    # Deviations 12000, -23000, 11000; squares sum to 794e6; sample variance 397e6.
    # sd = sqrt(397e6); t = mean / (sd / sqrt(3)).
    # Running total 5000, -25000, -21000: peak 5000 then fall to -25000 gives drawdown 30000.
    # One day at or below -20000 (the -30000 day). Months: Jan -25000 (negative), Feb +4000.
    # Halves at index 1: [5000] sums 5000 (positive); [-30000, 4000] sums -26000 (not positive).
    days = portfolio_days(EXAMPLE_TRADES, EXAMPLE_PICKS)
    summary = summarise(days)
    sd = math.sqrt(397e6)
    assert summary["n_trades_days"] == 3
    assert summary["net_total"] == -21000.0
    assert summary["mean_per_trading_day"] == -7000.0
    assert math.isclose(summary["sd"], sd)
    assert math.isclose(summary["t_stat"], -7000.0 / (sd / math.sqrt(3)))
    assert summary["worst_day"] == -30000.0
    assert summary["days_over_cap"] == 1
    assert summary["max_drawdown"] == 30000.0
    assert summary["positive_halves"] is False
    assert summary["months_negative"] == 1


def test_drawdown_is_measured_from_the_running_peak():
    # Running total 1000, -1000, 2000: the fall from 1000 to -1000 is 2000.
    # The new peak 2000 is never fallen from again, so the maximum is 2000.
    summary = summarise([("2026-01-01", 1000.0), ("2026-01-02", -2000.0), ("2026-01-03", 3000.0)])
    assert summary["max_drawdown"] == 2000.0


def test_positive_halves_and_clean_series():
    summary = summarise(PASSING_DAYS)
    assert summary["positive_halves"] is True
    assert summary["max_drawdown"] == 0.0
    assert summary["days_over_cap"] == 0
    assert summary["net_total"] == 10000.0
    assert summary["worst_day"] == 700.0
    expected_t = 1000.0 / (math.sqrt(280000 / 9) / math.sqrt(10))
    assert math.isclose(summary["t_stat"], expected_t)
    assert summary["t_stat"] > 2.0


def test_t_stat_is_zero_for_one_day_or_zero_sd():
    assert summarise([("2026-01-01", 500.0)])["t_stat"] == 0.0
    flat = summarise([("2026-01-01", 500.0), ("2026-01-02", 500.0)])
    assert flat["sd"] == 0.0
    assert flat["t_stat"] == 0.0


def test_no_trade_cells_contribute_nothing():
    picks = {"2026-01": {"c1": NO_TRADE, "c2": "A"}}
    trades = [
        _trade("2026-01-05", "A", "c1", 5000.0),
        _trade("2026-01-06", "A", "c2", 700.0),
    ]
    assert portfolio_days(trades, picks) == [("2026-01-06", 700.0)]


def test_month_comes_from_the_trade_own_date():
    picks = {
        "2026-01": {"c1": "B"},
        "2026-02": {"c1": "A"},
    }
    trades = [
        _trade("2026-02-01", "A", "c1", 700.0),  # February pick is A: counts
        _trade("2026-02-01", "B", "c1", 999.0),  # not the February pick: ignored
        _trade("2026-01-31", "A", "c1", 888.0),  # January pick is B: ignored
        _trade("2026-03-02", "A", "c1", 555.0),  # March has no pick: ignored
    ]
    assert portfolio_days(trades, picks) == [("2026-02-01", 700.0)]


def test_days_are_sorted_and_same_day_chosen_trades_are_summed():
    picks = {"2026-01": {"c1": "A", "c2": "A"}}
    trades = [
        _trade("2026-01-09", "A", "c1", 100.0),
        _trade("2026-01-03", "A", "c1", -250.0),
        _trade("2026-01-03", "A", "c2", 400.0),
    ]
    assert portfolio_days(trades, picks) == [("2026-01-03", 150.0), ("2026-01-09", 100.0)]


def test_hindsight_picks_best_mean_per_cell_with_name_tie_break():
    trades = [
        _trade("2026-01-01", "A", "c1", 1000.0),
        _trade("2026-01-02", "A", "c1", 3000.0),  # A on c1: mean 2000
        _trade("2026-01-01", "B", "c1", 2500.0),  # B on c1: mean 2500, best
        _trade("2026-01-03", "A", "c2", -500.0),  # A on c2: mean -500
        _trade("2026-01-03", "B", "c2", -100.0),  # B on c2: mean -100, best
        _trade("2026-01-04", "A", "c4", 100.0),  # tie on c4 at 100: name A wins
        _trade("2026-01-04", "B", "c4", 100.0),
    ]
    picks = hindsight_picks(trades, ["c1", "c2", "c3", "c4"], ["A", "B"])
    assert picks == {"c1": "B", "c2": "B", "c3": NO_TRADE, "c4": "A"}


def test_hindsight_days_uses_one_fixed_choice_per_cell():
    trades = [
        _trade("2026-01-01", "A", "c1", 1000.0),
        _trade("2026-01-01", "B", "c1", 2500.0),
        _trade("2026-01-03", "B", "c2", -100.0),
        _trade("2026-01-03", "A", "c2", -500.0),
    ]
    days = hindsight_days(trades, {"c1": "B", "c2": "B"})
    assert days == [("2026-01-01", 2500.0), ("2026-01-03", -100.0)]


def test_verdict_passes_a_clean_series():
    assert verdict(summarise(PASSING_DAYS)) == "eligible for forward shadow"


def test_verdict_t_statistic_branch_from_worked_example():
    summary = summarise(portfolio_days(EXAMPLE_TRADES, EXAMPLE_PICKS))
    assert verdict(summary) == "The t statistic is below 2.0."


def test_verdict_each_failure_branch_in_order():
    base = _passing_summary()

    weak = {**base, "t_stat": 1.99}
    assert verdict(weak) == "The t statistic is below 2.0."

    one_half = {**base, "positive_halves": False}
    assert verdict(one_half) == "The two halves of the period are not both positive."

    bad_day = {**base, "worst_day": -10000.0}
    assert verdict(bad_day) == "A single day lost 10,000 rupees or more."

    deep = {**base, "max_drawdown": 20000.0}
    assert verdict(deep) == "The largest drawdown is 20,000 rupees or more."

    over_cap = {**base, "days_over_cap": 1}
    assert verdict(over_cap) == "At least one day lost 27,000 rupees or more, the daily cap."


def test_verdict_reports_first_failed_condition_only():
    everything_wrong = {
        **_passing_summary(),
        "t_stat": 0.1,
        "positive_halves": False,
        "days_over_cap": 3,
    }
    assert verdict(everything_wrong) == "The t statistic is below 2.0."


def test_verdict_boundary_values():
    base = _passing_summary()
    assert verdict({**base, "t_stat": 2.0}) == "eligible for forward shadow"
    assert verdict({**base, "worst_day": -9999.0}) == "eligible for forward shadow"
    assert verdict({**base, "max_drawdown": 19999.0}) == "eligible for forward shadow"


def test_empty_input_returns_zeros_not_a_crash():
    summary = summarise([])
    assert summary == {
        "n_trades_days": 0,
        "net_total": 0.0,
        "mean_per_trading_day": 0.0,
        "sd": 0.0,
        "t_stat": 0.0,
        "worst_day": 0.0,
        "days_over_cap": 0,
        "max_drawdown": 0.0,
        "positive_halves": False,
        "months_negative": 0,
    }
    assert portfolio_days([], {}) == []
    assert hindsight_days([], {}) == []
    assert hindsight_picks([], ["c1"], ["A"]) == {"c1": NO_TRADE}
    assert verdict(summary) == "The t statistic is below 2.0."


def test_a_big_winning_day_does_not_fail_the_worst_day_check():
    good = {
        "t_stat": 3.0,
        "positive_halves": True,
        "worst_day": 12000.0,  # the smallest day is a gain: nothing was lost
        "max_drawdown": 1000.0,
        "days_over_cap": 0,
    }
    assert verdict(good) == "eligible for forward shadow"


def test_the_daily_cap_is_the_owners_27000():
    assert DAILY_CAP_RUPEES == 27000


def test_money_is_booked_on_exit_date_and_pick_uses_exit_month():
    picks = {"2026-01": {"c1": "A"}, "2026-02": {"c1": "B"}}
    # Entered on the last January session, closed on 2 February: the January pick (A) does not
    # apply, the February pick (B) does, and the net lands on the exit date.
    trade = {
        "date": "2026-01-30",
        "exit_date": "2026-02-02",
        "algo": "B",
        "cell": "c1",
        "net": 700.0,
    }
    assert portfolio_days([trade], picks) == [("2026-02-02", 700.0)]
    as_a = {**trade, "algo": "A"}
    assert portfolio_days([as_a], picks) == []


def test_exit_date_falls_back_to_entry_date_when_absent():
    picks = {"2026-01": {"c1": "A"}}
    trade = {"date": "2026-01-05", "algo": "A", "cell": "c1", "net": 300.0}
    assert portfolio_days([trade], picks) == [("2026-01-05", 300.0)]


def test_hindsight_days_books_on_exit_date():
    trade = {
        "date": "2026-01-30",
        "exit_date": "2026-02-02",
        "algo": "A",
        "cell": "c1",
        "net": 250.0,
    }
    assert hindsight_days([trade], {"c1": "A"}) == [("2026-02-02", 250.0)]
