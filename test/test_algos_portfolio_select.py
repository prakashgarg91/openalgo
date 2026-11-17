"""Tests for the walk-forward portfolio selector. Pure functions, no network."""

from services.algos.portfolio_select import (
    MIN_TRADES_PER_CELL,
    NO_TRADE,
    TRAILING_MONTHS,
    choose,
    exit_date_of,
    month_key,
    trailing_window,
    walk_forward_choices,
)


def trades(algo, cell, net, count, date="2025-06-15", exit_date=None):
    row = {"date": date, "exit_date": exit_date or date, "algo": algo, "cell": cell}
    return [{**row, "net": float(net)} for _ in range(count)]


def test_constants_are_frozen():
    assert TRAILING_MONTHS == 12
    assert MIN_TRADES_PER_CELL == 40
    assert NO_TRADE == "no_trade"


def test_month_key_takes_year_and_month():
    assert month_key("2026-03-31") == "2026-03"
    assert month_key("2025-12-01") == "2025-12"


def test_exit_date_falls_back_to_entry_date():
    assert exit_date_of({"date": "2026-01-05", "exit_date": "2026-01-06"}) == "2026-01-06"
    assert exit_date_of({"date": "2026-01-05"}) == "2026-01-05"


def test_trailing_window_includes_12_months_back_and_excludes_13():
    history = [
        {"date": "2025-10-20", "algo": "a", "cell": "x", "net": 1.0},  # 13 months back: out
        {"date": "2025-11-01", "algo": "a", "cell": "x", "net": 2.0},  # 12 months back: in
        {"date": "2026-10-31", "algo": "a", "cell": "x", "net": 3.0},  # last month: in
        {"date": "2026-11-01", "algo": "a", "cell": "x", "net": 4.0},  # the month itself: out
        {"date": "2026-12-05", "algo": "a", "cell": "x", "net": 5.0},  # later: out
    ]
    window = trailing_window(history, "2026-11")
    assert [t["net"] for t in window] == [2.0, 3.0]


def test_trailing_window_respects_months_argument():
    history = [{"date": "2026-08-01", "algo": "a", "cell": "x", "net": 1.0}]
    # August is 3 months before November: in a 3-month window, out of a 2-month window.
    assert len(trailing_window(history, "2026-11", months=3)) == 1
    assert trailing_window(history, "2026-11", months=2) == []


def test_window_is_keyed_on_exit_date_not_entry_date():
    # Entered 27 Feb 2026, closed 2 Mar 2026: the exit is in March.
    crossing = [
        {"date": "2026-02-27", "exit_date": "2026-03-02", "algo": "a", "cell": "x", "net": 1.0}
    ]
    # Not in the March window, because the result was not known until March.
    assert trailing_window(crossing, "2026-03") == []
    # In the April window: the March exit is a past month by then.
    assert len(trailing_window(crossing, "2026-04")) == 1


def test_trade_entered_on_last_session_counts_for_the_month_after_its_exit():
    # Entered 30 Jan 2026 (last session of January), exited 2 Feb 2026.
    history = trades("a", "x", 100, 40, date="2026-01-30", exit_date="2026-02-02")
    # The February pick must not see it: its exit is in February, the month being picked.
    assert choose(history, "2026-02", ["x"], ["a"]) == {"x": NO_TRADE}
    # The March pick sees it: the exit is in February, a past month.
    assert choose(history, "2026-03", ["x"], ["a"]) == {"x": "a"}


def test_no_look_ahead_for_the_same_month():
    history = trades("a", "x", 50, 40, date="2026-01-10")
    before = choose(history, "2026-03", ["x"], ["a"])
    extra = trades("b", "x", 10_000, 40, date="2026-03-02")  # the month itself
    extra += trades("b", "x", 10_000, 40, date="2026-04-02")  # later month
    after = choose(history + extra, "2026-03", ["x"], ["a", "b"])
    assert before == {"x": "a"}
    assert after == before


def test_adding_later_trades_does_not_change_earlier_walk_forward_months():
    history = trades("a", "x", 50, 40, date="2026-01-10")
    months = ["2026-02", "2026-03"]
    base = walk_forward_choices(history, months, ["x"], ["a"])
    later = history + trades("a", "x", -9_999, 60, date="2026-03-15")
    later_run = walk_forward_choices(later, months, ["x"], ["a"])
    assert later_run["2026-02"] == base["2026-02"]


def test_eligibility_threshold_is_40_trades():
    cells, algos = ["x"], ["a", "b"]
    thirty_nine = trades("a", "x", 100, 39) + trades("b", "x", 1, 40)
    assert choose(thirty_nine, "2026-03", cells, algos) == {"x": "b"}
    forty = trades("a", "x", 100, 40) + trades("b", "x", 1, 40)
    assert choose(forty, "2026-03", cells, algos) == {"x": "a"}


def test_non_positive_best_mean_gives_no_trade():
    cells, algos = ["x"], ["a"]
    losing = trades("a", "x", -5, 40)
    assert choose(losing, "2026-03", cells, algos) == {"x": NO_TRADE}
    flat = trades("a", "x", 0, 40)
    assert choose(flat, "2026-03", cells, algos) == {"x": NO_TRADE}


def test_no_eligible_algo_gives_no_trade():
    history = trades("a", "x", 100, 39)
    assert choose(history, "2026-03", ["x"], ["a"]) == {"x": NO_TRADE}
    assert choose([], "2026-03", ["x"], ["a"]) == {"x": NO_TRADE}


def test_tie_breaks_by_algo_name_regardless_of_list_order():
    history = trades("beta", "x", 10, 40) + trades("alpha", "x", 10, 40)
    assert choose(history, "2026-03", ["x"], ["beta", "alpha"]) == {"x": "alpha"}
    assert choose(history, "2026-03", ["x"], ["alpha", "beta"]) == {"x": "alpha"}


def test_event_and_unlabelled_are_always_no_trade():
    history = (
        trades("a", "event", 1_000, 40)
        + trades("a", "unlabelled", 1_000, 40)
        + trades("a", "x", 1_000, 40)
    )
    result = choose(history, "2026-03", ["event", "unlabelled", "x"], ["a"])
    assert result == {"event": NO_TRADE, "unlabelled": NO_TRADE, "x": "a"}


def test_worked_example_two_algos_two_cells():
    # Window for 2026-03 is exit months 2025-03 through 2026-02.
    # Cell X: A has 40 trades averaging 100, B has 40 averaging 50. A wins.
    # Cell Y: A has 40 trades averaging -10, so it is not positive. B has 40 trades, 10 at +30
    #   and 30 at 0, averaging 7.5. B is eligible and positive, so B wins.
    history = (
        trades("a", "x", 100, 40, date="2025-06-01")
        + trades("b", "x", 50, 40, date="2025-07-01")
        + trades("a", "y", -10, 40, date="2025-08-01")
        + trades("b", "y", 30, 10, date="2025-09-01")
        + trades("b", "y", 0, 30, date="2025-09-02")
    )
    # Noise that must be ignored: a huge B trade exited in the month itself, one exited 13 months
    # back, and a huge A trade in Y exited in a later month.
    history += [
        {"date": "2026-03-04", "exit_date": "2026-03-04", "algo": "b", "cell": "x", "net": 1e9},
        {"date": "2025-02-20", "exit_date": "2025-02-20", "algo": "a", "cell": "y", "net": 1e9},
        {"date": "2026-04-01", "exit_date": "2026-04-01", "algo": "a", "cell": "y", "net": 1e9},
    ]
    assert choose(history, "2026-03", ["x", "y"], ["a", "b"]) == {"x": "a", "y": "b"}


def test_walk_forward_returns_one_choice_per_month():
    history = trades("a", "x", 100, 40, date="2025-06-01")
    result = walk_forward_choices(history, ["2026-02", "2026-03"], ["x"], ["a"])
    assert set(result) == {"2026-02", "2026-03"}
    assert result["2026-02"] == {"x": "a"}
    assert result["2026-03"] == {"x": "a"}


def test_evidence_expires_after_twelve_months():
    history = trades("a", "x", 100, 40, date="2025-06-01")
    result = walk_forward_choices(history, ["2026-06", "2026-07"], ["x"], ["a"])
    # 2026-06 window is 2025-06..2026-05, which holds the June 2025 trades.
    assert result["2026-06"] == {"x": "a"}
    # 2026-07 window is 2025-07..2026-06, so the June 2025 trades have expired.
    assert result["2026-07"] == {"x": NO_TRADE}
