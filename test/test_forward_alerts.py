"""Telegram alert messages for the forward shadow test."""

from datetime import date

import pandas as pd

from services.algos import forward_alerts as fa


def test_a_clean_capture_says_nothing_and_each_failure_says_what_to_do():
    assert fa.capture_message(0, "2026-11-06") is None
    assert "analytics token" in fa.capture_message(3, "2026-11-06")
    assert "could not be saved" in fa.capture_message(2, "2026-11-06")
    assert "log\\capture.log" in fa.capture_message(1, "2026-11-06")
    for code in (1, 2, 3):
        text = fa.capture_message(code, "2026-11-06")
        assert "HTTP" not in text and "Traceback" not in text


def test_a_missed_weekday_is_named_and_a_holiday_can_be_excused():
    stored = [pd.Timestamp("2026-11-05")]
    msg = fa.missing_day_message(stored, date(2026, 11, 9))
    assert "Fri 06 Nov" in msg and "Mon" not in msg
    assert fa.missing_day_message(stored, date(2026, 11, 9), {date(2026, 11, 6)}) is None
    assert fa.missing_day_message(stored, date(2026, 11, 6)) is None  # today is not checked
    assert "No option candles are stored yet" in fa.missing_day_message([], date(2026, 11, 6))


def report(**over):
    ledger = {
        "completed": 1,
        "realistic_net": 600,
        "not_counted": [{"expiry": "2026-11-10", "reason": "expiry day only partly stored"}],
        "open": [{"expiry": "2026-11-17 00:00", "entry": "2026-11-13 10:15", "credit": 14.5}],
        "trades": [{"expiry": "2026-11-24 00:00", "net": 600.0}],
        "status": {"state": "running", "verdict": None},
    }
    return {"ledgers": {"L1": {**ledger, **over}}}


def test_each_event_is_sent_once_only():
    first, seen = fa.events(report(), set())
    assert len(first) == 3
    assert any("NOT counted" in m for m in first)
    assert any("1 of 26" in m for m in first)
    second, seen = fa.events(report(), seen)
    assert second == []


def test_a_stop_is_announced_once():
    stopped = report(status={"state": "stopped", "verdict": "fail"})
    msgs, seen = fa.events(stopped, set())
    assert any("stopped" in m for m in msgs)
    again, _ = fa.events(stopped, seen)
    assert again == []
