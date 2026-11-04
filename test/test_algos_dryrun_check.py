"""Tests for the pure dry-run readiness check in services/algos/dryrun_check.py."""

from datetime import date

from services.algos.dryrun_check import (
    EXPECTED_LOT,
    REQUIRED_TASKS,
    Facts,
    evaluate,
    summary,
)

TASK_TEXT = "05-11-2026 10:15:00"


def make(**overrides) -> Facts:
    base = {
        "app_up": True,
        "key_set": True,
        "mode": "analyze",
        "quote_ok": True,
        "today": date(2026, 11, 4),
        "expiry": date(2026, 11, 9),
        "entry_day": date(2026, 11, 5),
        "lot_qty": 65,
        "legs": "two_sided",
        "market_open": True,
        "tasks": dict.fromkeys(REQUIRED_TASKS, TASK_TEXT),
    }
    base.update(overrides)
    return Facts(**base)


def by_check(rows, check):
    matches = [row for row in rows if row[1] == check]
    assert len(matches) == 1, f"expected one row for {check!r}, got {rows}"
    return matches[0]


def fails(rows):
    return [row for row in rows if row[0] == "fail"]


def warns(rows):
    return [row for row in rows if row[0] == "warn"]


# Healthy case and summary


def test_healthy_case_has_no_fail_rows():
    rows = evaluate(make())
    assert fails(rows) == []


def test_healthy_case_summary_is_ready():
    rows = evaluate(make())
    ready, headline = summary(rows)
    assert ready is True
    assert headline == "Ready for the dry run."


def test_healthy_case_has_only_the_computer_warning():
    rows = evaluate(make())
    assert [row[1] for row in warns(rows)] == ["Computer"]


def test_computer_warning_alone_still_ready_for_dry_run():
    rows = [
        ("ok", "OpenAlgo", "x"),
        ("warn", "Computer", "x"),
    ]
    assert summary(rows) == (True, "Ready for the dry run.")


def test_headline_ready_with_confirmations_when_other_warning():
    rows = [("ok", "OpenAlgo", "x"), ("warn", "Entry day", "x")]
    assert summary(rows) == (True, "Ready, with things to confirm.")


def test_headline_counts_failures():
    rows = [
        ("fail", "Mode", "x"),
        ("fail", "Quantity", "x"),
        ("ok", "Expiry", "x"),
    ]
    ready, headline = summary(rows)
    assert ready is False
    assert headline == "Not ready: 2 problem(s)."


def test_headline_with_warning_and_no_fail_is_ready_with_confirmations():
    rows = [("warn", "Mode", "x"), ("ok", "Expiry", "x")]
    assert summary(rows) == (True, "Ready, with things to confirm.")


# OpenAlgo rule


def test_app_down_returns_exactly_one_fail_row():
    rows = evaluate(make(app_up=False))
    assert len(rows) == 1
    assert rows[0][0] == "fail"
    assert rows[0][1] == "OpenAlgo"
    assert rows[0][2] == "OpenAlgo is not answering. Start it with Start-OpenAlgo.bat."


def test_app_down_summary_is_not_ready():
    ready, headline = summary(evaluate(make(app_up=False)))
    assert ready is False
    assert headline == "Not ready: 1 problem(s)."


def test_app_up_reports_ok_first():
    rows = evaluate(make())
    assert rows[0] == ("ok", "OpenAlgo", "OpenAlgo is running.")


# API key rule


def test_key_missing_returns_exactly_two_rows():
    rows = evaluate(make(key_set=False))
    assert len(rows) == 2
    assert rows[0][1] == "OpenAlgo"
    assert rows[1] == ("fail", "API key", "OPENALGO_API_KEY is not set for this Windows user.")


def test_key_set_reports_ok():
    assert by_check(evaluate(make()), "API key") == ("ok", "API key", "Set.")


# Mode rule


def test_analyze_mode_is_ok():
    assert by_check(evaluate(make(mode="analyze")), "Mode") == (
        "ok",
        "Mode",
        "Analyze (sandbox) mode is on.",
    )


def test_live_mode_fails():
    row = by_check(evaluate(make(mode="live")), "Mode")
    assert row == (
        "fail",
        "Mode",
        "OpenAlgo is in Live mode. Switch to Analyze before the bot runs.",
    )


def test_unknown_mode_is_warn():
    row = by_check(evaluate(make(mode=None)), "Mode")
    assert row[0] == "warn"


# Broker session rule


def test_no_quote_fails():
    row = by_check(evaluate(make(quote_ok=False)), "Broker session")
    assert row[0] == "fail"
    assert "Sign in to Upstox again" in row[2]


def test_quote_ok_is_ok():
    assert by_check(evaluate(make(quote_ok=True)), "Broker session")[0] == "ok"


# Expiry rule


def test_expiry_none_fails():
    row = by_check(evaluate(make(expiry=None, entry_day=None)), "Expiry")
    assert row == ("fail", "Expiry", "No Nifty expiry found. Download the master contract.")


def test_expiry_formats_date():
    row = by_check(evaluate(make()), "Expiry")
    assert row == ("ok", "Expiry", "Nearest weekly expiry is Mon 09 Nov 2026.")


# Entry day rule


def test_entry_day_none_is_warn():
    row = by_check(evaluate(make(entry_day=None)), "Entry day")
    assert row == ("warn", "Entry day", "Could not work out the entry day.")


def test_entry_day_today_is_ok():
    row = by_check(evaluate(make(entry_day=date(2026, 11, 4))), "Entry day")
    assert row == ("ok", "Entry day", "Today is the entry session.")


def test_entry_day_future_states_days_ahead():
    row = by_check(evaluate(make(entry_day=date(2026, 11, 5))), "Entry day")
    assert row == ("ok", "Entry day", "The bot enters on Thu 05 Nov, in 1 day(s).")


def test_entry_day_passed_is_warn():
    row = by_check(evaluate(make(entry_day=date(2026, 11, 3))), "Entry day")
    assert row == (
        "warn",
        "Entry day",
        "The entry session (Tue 03 Nov) has already passed for this expiry.",
    )


# Quantity rule


def test_expected_lot_is_ok():
    row = by_check(evaluate(make(lot_qty=EXPECTED_LOT)), "Quantity")
    assert row == ("ok", "Quantity", "The bot will send 65 (one lot).")


def test_wrong_lot_fails():
    row = by_check(evaluate(make(lot_qty=130)), "Quantity")
    assert row == ("fail", "Quantity", "The bot would send 130, expected 65.")


def test_lot_none_is_warn():
    row = by_check(evaluate(make(lot_qty=None)), "Quantity")
    assert row == ("warn", "Quantity", "Could not work out the quantity.")


# Option prices rule


def test_two_sided_legs_ok():
    row = by_check(evaluate(make(legs="two_sided")), "Option prices")
    assert row == ("ok", "Option prices", "Both options have a bid and an ask.")


def test_no_legs_with_market_closed_is_warn_not_fail():
    row = by_check(evaluate(make(legs="none", market_open=False)), "Option prices")
    assert row[0] == "warn"
    assert row[2] == "The market is closed, so bid and ask cannot be checked until it opens."


def test_no_legs_with_market_open_is_fail():
    row = by_check(evaluate(make(legs="none", market_open=True)), "Option prices")
    assert row == ("fail", "Option prices", "One of the two options has no bid or ask right now.")


def test_unknown_legs_is_warn():
    row = by_check(evaluate(make(legs="unknown")), "Option prices")
    assert row == ("warn", "Option prices", "Option prices were not checked.")


# Scheduled tasks rule


def test_missing_task_fails():
    tasks = dict.fromkeys(REQUIRED_TASKS, TASK_TEXT)
    tasks[REQUIRED_TASKS[0]] = None
    rows = evaluate(make(tasks=tasks))
    row = by_check(rows, REQUIRED_TASKS[0])
    assert row == (
        "fail",
        REQUIRED_TASKS[0],
        f"The scheduled task '{REQUIRED_TASKS[0]}' is missing.",
    )


def test_task_absent_from_dict_fails():
    tasks = {REQUIRED_TASKS[0]: TASK_TEXT}
    rows = evaluate(make(tasks=tasks))
    row = by_check(rows, REQUIRED_TASKS[1])
    assert row[0] == "fail"


def test_present_tasks_report_next_run():
    rows = evaluate(make())
    for name in REQUIRED_TASKS:
        assert by_check(rows, name) == ("ok", name, f"{name}: next run {TASK_TEXT}")


# Computer row


def test_computer_row_is_always_last_and_warn():
    # The early returns for "OpenAlgo down" and "no API key" stop before the
    # Computer row, so only the full-evaluation cases carry it.
    for facts in (
        make(),
        make(mode="live", quote_ok=False),
        make(legs="none", market_open=False),
    ):
        rows = evaluate(facts)
        assert rows[-1] == (
            "warn",
            "Computer",
            "The PC must be on and signed in before 10:15. A powered-off PC cannot run the bot or the snapshots.",
        )


def test_computer_row_is_present_once_in_full_run():
    rows = evaluate(make())
    assert [row[1] for row in rows].count("Computer") == 1


def test_row_order_in_full_run():
    rows = evaluate(make())
    names = [row[1] for row in rows]
    assert names == [
        "OpenAlgo",
        "API key",
        "Mode",
        "Broker session",
        "Expiry",
        "Entry day",
        "Quantity",
        "Option prices",
        *REQUIRED_TASKS,
        "Computer",
    ]
