"""Rules of the daily check (morning, midday, evening) and its CLI, on made-up facts.

The CLI test replaces the collector and the Telegram sender, so nothing reads the real system and
nothing is sent. Its log is written inside tmp_path.
"""

import importlib.util
from datetime import date
from pathlib import Path

import pytest

from services.algos import daily_check as dc
from services.algos import forward_alerts as fa

TODAY = date(2026, 11, 9)  # a Monday


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts/algo_backtest/daily_check.py"
    spec = importlib.util.spec_from_file_location("algo_daily_check_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()


def facts(**overrides) -> dc.Facts:
    base = {
        "when": "morning",
        "today": TODAY,
        "app_up": True,
        "key_set": True,
        "mode": "analyze",
        "quote_ok": True,
        "snapshot_labels": set(),
        "capture_problems": None,
        "yesterday_capture_ok": True,
        "zen_file_age_days": 2.0,
    }
    base.update(overrides)
    return dc.Facts(**base)


def levels(rows):
    return {check: level for level, check, _ in rows}


def level_of(rows, check):
    return levels(rows).get(check)


def message_of(rows, check):
    return next(message for _, name, message in rows if name == check)


# Morning: healthy


def test_morning_healthy_is_all_clear():
    rows = dc.evaluate(facts())
    assert all(level == "ok" for level, _, _ in rows)
    assert dc.headline(rows) == "All clear."
    assert dc.should_alert(rows) is False


# Morning: OpenAlgo


def test_morning_app_down_is_a_fail_and_skips_mode_and_session():
    rows = dc.evaluate(facts(app_up=False, mode=None, quote_ok=False))
    assert level_of(rows, "OpenAlgo") == "fail"
    assert message_of(rows, "OpenAlgo") == (
        "OpenAlgo is not running. Start it with Start-OpenAlgo.bat."
    )
    assert "Mode" not in levels(rows)
    assert "Broker session" not in levels(rows)
    assert dc.should_alert(rows) is True


def test_morning_key_missing_is_a_fail():
    rows = dc.evaluate(facts(key_set=False, mode=None, quote_ok=False))
    assert level_of(rows, "API key") == "fail"
    assert "Mode" not in levels(rows)
    assert dc.should_alert(rows) is True


# Morning: mode


def test_morning_live_mode_is_a_fail():
    rows = dc.evaluate(facts(mode="live"))
    assert level_of(rows, "Mode") == "fail"
    assert message_of(rows, "Mode") == "OpenAlgo is in Live mode. Switch to Analyze."
    assert dc.should_alert(rows) is True


def test_morning_unknown_mode_is_a_warn_and_no_alert():
    rows = dc.evaluate(facts(mode=None))
    assert level_of(rows, "Mode") == "warn"
    assert dc.should_alert(rows) is False


# Morning: broker session


def test_morning_quote_missing_is_a_fail_with_the_login_advice():
    rows = dc.evaluate(facts(quote_ok=False))
    assert level_of(rows, "Broker session") == "fail"
    assert message_of(rows, "Broker session") == (
        "Upstox is not connected. Sign in to Upstox (the login expires every morning), "
        "then switch to Analyze."
    )
    assert dc.should_alert(rows) is True


# Morning: yesterday and the Zen file


def test_morning_yesterday_capture_not_finished_is_a_warn():
    rows = dc.evaluate(facts(yesterday_capture_ok=False))
    assert level_of(rows, "Yesterday's capture") == "warn"
    assert message_of(rows, "Yesterday's capture") == "Yesterday's capture did not finish."
    assert dc.should_alert(rows) is False


def test_morning_yesterday_not_asked_adds_no_row():
    rows = dc.evaluate(facts(yesterday_capture_ok=None))
    assert "Yesterday's capture" not in levels(rows)


def test_morning_zen_file_older_than_ten_days_is_a_warn():
    rows = dc.evaluate(facts(zen_file_age_days=11.4))
    assert level_of(rows, "Zen trade file") == "warn"
    assert message_of(rows, "Zen trade file") == "The Zen trade file is 11 days old."
    assert dc.should_alert(rows) is False


def test_morning_zen_file_ten_days_old_is_still_ok():
    rows = dc.evaluate(facts(zen_file_age_days=10.0))
    assert level_of(rows, "Zen trade file") == "ok"


def test_morning_zen_file_missing_adds_no_row():
    rows = dc.evaluate(facts(zen_file_age_days=None))
    assert "Zen trade file" not in levels(rows)


# Midday


def test_midday_snapshot_present_is_ok():
    rows = dc.evaluate(facts(when="midday", snapshot_labels={"1015"}))
    assert rows == [("ok", "10:15 snapshot", "The 10:15 bid-ask snapshot is saved.")]
    assert dc.should_alert(rows) is False


def test_midday_snapshot_missing_is_a_fail():
    rows = dc.evaluate(facts(when="midday", snapshot_labels={"1430"}))
    assert level_of(rows, "10:15 snapshot") == "fail"
    assert message_of(rows, "10:15 snapshot") == (
        "The 10:15 bid-ask snapshot did not arrive. Check that the PC was on and "
        "OpenAlgo was signed in."
    )
    assert dc.should_alert(rows) is True


# Evening


def test_evening_complete_capture_is_ok():
    rows = dc.evaluate(facts(when="evening", capture_problems=[]))
    assert rows == [("ok", "Today's capture", "Today's capture and checks are complete.")]
    assert dc.should_alert(rows) is False


def test_evening_problems_are_a_fail_with_them_joined():
    problems = ["the database snapshot was not written", "bid-ask snapshots missing: 1430"]
    rows = dc.evaluate(facts(when="evening", capture_problems=problems))
    assert level_of(rows, "Today's capture") == "fail"
    message = message_of(rows, "Today's capture")
    assert "the database snapshot was not written; bid-ask snapshots missing: 1430" in message
    assert dc.should_alert(rows) is True


def test_evening_not_checked_is_a_warn():
    rows = dc.evaluate(facts(when="evening", capture_problems=None))
    assert level_of(rows, "Today's capture") == "warn"
    assert dc.should_alert(rows) is False


# Headline and alert


def test_headline_counts_fails_and_warns_and_names_the_first_checks():
    rows = [
        ("ok", "OpenAlgo", "x"),
        ("fail", "Broker session", "x"),
        ("warn", "Mode", "x"),
        ("fail", "Expiry", "x"),
        ("warn", "Zen trade file", "x"),
    ]
    assert dc.headline(rows) == ("2 problem(s), 2 to confirm: Broker session, Mode, Expiry")


def test_headline_warn_only_counts_zero_problems():
    rows = [("warn", "Mode", "x")]
    assert dc.headline(rows) == "0 problem(s), 1 to confirm: Mode"


def test_should_alert_only_on_fail():
    assert dc.should_alert([("warn", "Mode", "x"), ("ok", "API key", "x")]) is False
    assert dc.should_alert([("warn", "Mode", "x"), ("fail", "API key", "x")]) is True
    assert dc.should_alert([]) is False


# Collector helpers


def test_previous_weekday_skips_the_weekend():
    assert script.previous_weekday(date(2026, 11, 9)) == date(2026, 11, 6)  # Monday -> Friday
    assert script.previous_weekday(date(2026, 11, 10)) == date(2026, 11, 9)  # Tuesday -> Monday


def test_yesterday_without_a_block_in_the_log_is_not_ok(monkeypatch):
    monkeypatch.setattr(script, "read_capture_text", lambda: "")
    monkeypatch.setattr(script, "read_labels", lambda day: set())
    assert script.read_yesterday_ok(TODAY) is False


# CLI


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_notify(message):
        calls.append(message)
        return True

    monkeypatch.setattr(fa, "notify", fake_notify)
    return calls


def use_facts(monkeypatch, value):
    monkeypatch.setattr(script, "collect", lambda when, now: value)


def test_cli_healthy_exits_zero_writes_log_and_does_not_alert(run_dir, monkeypatch, sent, capsys):
    use_facts(monkeypatch, facts())
    code = script.main(["morning"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[OK  ] OpenAlgo: OpenAlgo is running." in out
    assert out.strip().splitlines()[-1] == "All clear."
    log = (run_dir / "log" / "daily_check.log").read_text(encoding="utf-8")
    assert "Daily check (morning) for 2026-11-09" in log
    assert sent == []


def test_cli_failure_exits_one_and_alerts_with_the_failing_checks(
    run_dir, monkeypatch, sent, capsys
):
    use_facts(monkeypatch, facts(when="midday", snapshot_labels=set()))
    code = script.main(["midday"])
    assert code == 1
    assert len(sent) == 1
    assert sent[0].startswith("Daily check (midday, Mon 09 Nov): 1 problem(s)")
    assert "10:15 snapshot: The 10:15 bid-ask snapshot did not arrive." in sent[0]


def test_cli_no_alert_flag_skips_telegram_but_still_fails(run_dir, monkeypatch, sent):
    use_facts(monkeypatch, facts(when="midday", snapshot_labels=set()))
    assert script.main(["midday", "--no-alert"]) == 1
    assert sent == []


def test_cli_warning_only_exits_zero_and_does_not_alert(run_dir, monkeypatch, sent):
    use_facts(monkeypatch, facts(mode=None))
    assert script.main(["morning"]) == 0
    assert sent == []


def test_cli_telegram_failure_does_not_crash(run_dir, monkeypatch, capsys):
    def broken_notify(message):
        raise RuntimeError("bot offline")

    monkeypatch.setattr(fa, "notify", broken_notify)
    use_facts(monkeypatch, facts(app_up=False, mode=None, quote_ok=False))
    assert script.main(["morning"]) == 1
    assert "could not be sent" in capsys.readouterr().out


def test_cli_evening_problems_fail(run_dir, monkeypatch, sent):
    use_facts(
        monkeypatch, facts(when="evening", capture_problems=["bid-ask snapshots missing: 1500"])
    )
    assert script.main(["evening"]) == 1
    assert "bid-ask snapshots missing: 1500" in sent[0]


def test_cli_rejects_an_unknown_checkpoint(run_dir, monkeypatch, capsys):
    use_facts(monkeypatch, facts())
    assert script.main(["noon"]) == 2
    assert "morning|midday|evening" in capsys.readouterr().out
