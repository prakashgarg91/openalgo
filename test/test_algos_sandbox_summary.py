"""Tests for the 15:30 Sandbox summary: services/algos/sandbox_summary.py and its read-only CLI.

Pure tests for the service. The CLI tests use temporary files only and never touch db/ or log/.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from services.algos import forward_alerts
from services.algos import sandbox_summary as ss
from services.algos.sandbox_round_trips import fill_charges

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "algo_backtest" / "sandbox_summary.py"
DAY = "2026-11-18"
STAMP = "18-11-2026"


def hm(text: str) -> int:
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def check_lines(missing: tuple[str, ...] = (), day: str = STAMP) -> list[str]:
    """One 'check' header per grid mark, except the marks named in ``missing`` (as HH:MM)."""
    skip = {hm(m) for m in missing}
    lines = [f"==== {day} {m // 60:02d}:{m % 60:02d}:07 check" for m in ss.GRID if m not in skip]
    return ["==== 18-11-2026 09:20:01 entry", "some unrelated line"] + lines


def open_state(**extra) -> dict:
    return {
        "status": "open",
        "entry_date": DAY,
        "expiry": "2026-11-24",
        "exit_session": "2026-11-19",
        "sold": "NIFTY24NOV2626000CE",
        "long": "NIFTY24NOV2626200CE",
        "sold_strike": 26000,
        "bought_strike": 26200,
        "entry_ltp_credit": 62.5,
        "short_fill": {"price": 61.0},
        "hedge_fill": {"price": 30.0},
        "credit_points": 31.0,
        **extra,
    }


def closed_row(**extra) -> dict:
    return {
        "entry_date": "2026-11-17",
        "entry_time": "2026-11-17 10:16",
        "expiry": "2026-11-24",
        "exit_session": DAY,
        "sold": "NIFTY24NOV2626000CE",
        "long": "NIFTY24NOV2626200CE",
        "quantity": "65",
        "short_fill_price": "100.0",
        "hedge_fill_price": "80.0",
        "buyback_fill_price": "50.0",
        "sell_hedge_fill_price": "40.0",
        "exit_time": f"{DAY} 15:26",
        "exit_reason": "TARGET",
        "gross_rupees": "1300.0",
        **extra,
    }


def run(state=None, trades=None, log=None, day=DAY):
    return ss.build_summary(
        state if state is not None else {},
        trades or [],
        log if log is not None else check_lines(),
        ss.EXPECTED_CHECKS,
        day,
    )


def test_expected_checks_is_74_from_0920_to_1525():
    assert ss.EXPECTED_CHECKS == 74
    assert ss.GRID[0] == hm("09:20") and ss.GRID[-1] == hm("15:25")


def test_clean_day_with_an_open_trade():
    summary = run(open_state())
    assert summary["verdict"] == "clean day"
    assert summary["clean"] is True
    assert summary["checks"] == {"run": 74, "expected": 74, "missed": 0, "missed_at": []}
    assert summary["gaps"] == []
    assert summary["state"]["status"] == "open"
    assert summary["state"]["credit_fill"] == 31.0
    assert summary["state"]["entry_ltp_credit"] == 62.5


def test_a_single_missed_check_is_counted_but_not_a_gap():
    summary = run(open_state(), log=check_lines(missing=("09:40", "13:05")))
    assert summary["checks"]["missed"] == 2
    assert summary["checks"]["missed_at"] == ["09:40", "13:05"]
    assert summary["gaps"] == []
    assert summary["verdict"] == "clean day"


def test_two_missed_checks_in_a_row_make_a_gap():
    summary = run(open_state(), log=check_lines(missing=("11:00", "11:05")))
    assert summary["verdict"] == "check gaps: 1"
    assert summary["gaps"] == [
        {"from": "11:00", "to": "11:05", "reason": "two or more checks missed in a row"}
    ]


def closed_on_exit_day(**extra) -> dict:
    """A trade that closed on its exit day: the state says closed, so only the gap rule applies."""
    return open_state(status="closed", exit_session=DAY, **extra)


def test_exit_day_gap_at_1500_is_a_gap():
    summary = run(closed_on_exit_day(), trades=[closed_row()], log=check_lines(missing=("15:00",)))
    assert summary["verdict"] == "check gaps: 1"
    assert summary["gaps"][0]["from"] == "15:00"
    assert "14:55 and 15:05" in summary["gaps"][0]["reason"]


def test_missing_1500_on_a_non_exit_day_is_not_a_gap():
    summary = run(open_state(exit_session="2026-11-19"), log=check_lines(missing=("15:00",)))
    assert summary["gaps"] == []
    assert summary["verdict"] == "clean day"


def test_missing_1520_on_the_exit_day_is_not_in_the_window():
    summary = run(closed_on_exit_day(), trades=[closed_row()], log=check_lines(missing=("15:20",)))
    assert summary["gaps"] == []
    assert summary["verdict"] == "clean day"


def test_open_trade_on_its_exit_day_needs_attention_even_with_checks_clean():
    summary = run(open_state(exit_session=DAY), log=check_lines(missing=("15:00",)))
    assert summary["verdict"] == "needs attention: open"


def test_a_run_that_is_not_a_check_or_not_today_is_ignored():
    log = check_lines() + ["==== 17-11-2026 10:00:00 check", "==== 18-11-2026 10:00:00 entry"]
    summary = run(open_state(), log=log)
    assert summary["checks"]["run"] == 74


def test_needs_attention_names_the_state():
    summary = run({"status": "orphan_hedge", "exit_session": "2026-11-19"})
    assert summary["verdict"] == "needs attention: orphan_hedge"
    assert summary["clean"] is False


def test_attention_wins_over_a_check_gap():
    summary = run({"status": "needs_attention"}, log=check_lines(missing=("11:00", "11:05")))
    assert summary["verdict"] == "needs attention: needs_attention"
    assert summary["gaps"]


def test_open_past_its_exit_session_needs_attention():
    summary = run(open_state(exit_session=DAY))
    assert summary["verdict"] == "needs attention: open"


def test_no_trade_recorded_is_a_clean_day():
    summary = run({})
    assert summary["state"]["status"] == "none"
    assert summary["verdict"] == "clean day"


def test_closed_trade_is_netted_by_the_research_charges():
    row = closed_row()
    qty = 65.0
    charges = (
        fill_charges("SELL", qty, 100.0, "2026-11-17")
        + fill_charges("BUY", qty, 80.0, "2026-11-17")
        + fill_charges("BUY", qty, 50.0, DAY)
        + fill_charges("SELL", qty, 40.0, DAY)
    )
    summary = run({**open_state(status="closed", exit_session=DAY)}, trades=[row])
    trade = summary["closed_today"][0]
    assert trade["gross"] == 1300.0
    assert trade["charges"] == pytest.approx(round(charges, 2), abs=0.01)
    assert trade["net"] == pytest.approx(round(1300.0 - charges, 2), abs=0.01)
    assert summary["net_today"] == trade["net"]
    assert summary["cumulative_net"] == trade["net"]


def test_cumulative_net_skips_a_trade_without_fill_prices():
    old = closed_row(exit_time="2026-11-10 15:26", buyback_fill_price="", entry_date="2026-11-09")
    summary = run({"status": "closed"}, trades=[old, closed_row()])
    assert summary["unpriced_trades"] == 1
    assert summary["closed_today"][0]["net"] is not None
    assert summary["cumulative_net"] == summary["net_today"]


def test_render_text_is_plain_and_starts_with_the_heading():
    summary = run(open_state(), log=check_lines(missing=("09:40",)))
    text = ss.render_text(summary)
    assert text.startswith("Sandbox 15:30 summary: 18 Nov 2026. Verdict: clean day.")
    assert "Checks: 73 logged of 74 expected, 1 missed, missed at 09:40." in text
    assert "Gaps: none." in text
    assert "Closed today: none." in text
    assert "Cumulative net after charges: Rs 0." in text


def test_render_text_reports_a_closed_trade_and_a_gap():
    summary = run(
        open_state(status="closed", exit_session=DAY),
        trades=[closed_row()],
        log=check_lines(missing=("11:00", "11:05")),
    )
    text = ss.render_text(summary)
    assert "Verdict: check gaps: 1." in text
    assert "11:00 to 11:05" in text
    assert "Closed today: 1 trade(s), net after charges Rs" in text


def test_recent_runs_returns_the_last_three_headers():
    log = [
        "==== 18-11-2026 09:20:01 check",
        "noise",
        "==== 18-11-2026 09:25:01 check",
        "==== 18-11-2026 09:30:01 check",
        "==== 18-11-2026 09:35:01 check",
    ]
    assert ss.recent_runs(log, 3) == [
        "==== 18-11-2026 09:25:01 check",
        "==== 18-11-2026 09:30:01 check",
        "==== 18-11-2026 09:35:01 check",
    ]


def _cli():
    spec = importlib.util.spec_from_file_location("sandbox_summary_cli_test", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_files(tmp_path: Path, state: dict | None, log: list[str] | None, trades=None):
    state_path = tmp_path / "state.json"
    trades_path = tmp_path / "trades.csv"
    log_path = tmp_path / "bot.log"
    if state is not None:
        state_path.write_text(json.dumps(state), encoding="utf-8")
    if log is not None:
        log_path.write_text("\n".join(log) + "\n", encoding="utf-8")
    if trades is not None:
        import csv

        with trades_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(trades[0].keys()))
            writer.writeheader()
            writer.writerows(trades)
    return ["--state", str(state_path), "--trades", str(trades_path), "--log", str(log_path)]


def test_cli_summary_reads_temp_files_and_says_read_only(tmp_path, capsys):
    files = _write_files(tmp_path, open_state(), check_lines(), trades=[closed_row()])
    code = _cli().main(["summary", *files, "--date", DAY])
    out = capsys.readouterr().out
    assert code == 0
    assert "This view is read only and places no order." in out
    assert "Sandbox 15:30 summary: 18 Nov 2026. Verdict: clean day." in out


def test_cli_summary_with_missing_files_still_runs(tmp_path, capsys):
    files = _write_files(tmp_path, None, None)
    assert _cli().main(["summary", *files, "--date", DAY]) == 0
    out = capsys.readouterr().out
    assert "No trade in the bot state." in out
    assert "Checks: 0 logged of 74 expected, 74 missed" in out


def test_cli_status_shows_state_and_the_last_three_runs(tmp_path, capsys):
    log = check_lines()
    files = _write_files(tmp_path, open_state(), log)
    assert _cli().main(["status", *files]) == 0
    out = capsys.readouterr().out
    assert "This view is read only and places no order." in out
    assert '"status": "open"' in out
    assert "Last 3 log runs:" in out
    assert out.count("==== 18-11-2026") == 3
    assert "==== 18-11-2026 15:25:07 check" in out


def test_cli_notify_sends_the_text_through_forward_alerts(tmp_path, capsys, monkeypatch):
    sent: list[str] = []

    def fake_notify(message: str) -> bool:
        sent.append(message)
        return False

    monkeypatch.setattr(forward_alerts, "notify", fake_notify)
    files = _write_files(tmp_path, open_state(), check_lines())
    assert _cli().main(["summary", *files, "--date", DAY, "--notify"]) == 0
    assert len(sent) == 1
    assert sent[0].startswith("Sandbox 15:30 summary:")
    assert "Not sent to Telegram" in capsys.readouterr().out
