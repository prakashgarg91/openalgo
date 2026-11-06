"""Tests for the shadow follow ledger of Zen's advices (services/algos/zen_follow.py and its script)."""

import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from services.algos import zen_follow as zf
from services.algos.eod_screen import leg_cost
from services.algos.zen_trades import ZenTrade

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "algo_backtest" / "run_zen_follow.py"
IST = timezone(timedelta(hours=5, minutes=30))


def make_trade(
    advice_id="a1",
    entry_day=date(2026, 9, 7),
    kind="PE",
    sold=(100.0, 30.0),
    long=(40.0, 10.0),
    closed=True,
    lot_size=50,
):
    """A trade with leg prices. sold and long are (entry, exit) in points."""
    sold_entry, sold_exit = sold
    long_entry, long_exit = long
    entry_time = datetime(entry_day.year, entry_day.month, entry_day.day, 10, 0, tzinfo=IST)
    exit_time = entry_time.replace(hour=15) if closed else None
    return ZenTrade(
        advice_id=advice_id,
        entry_time=entry_time,
        exit_time=exit_time,
        kind=kind,
        sold_symbol="NIFTY2690723000PE",
        long_symbol="NIFTY2690722900PE",
        sold_strike=23000.0,
        long_strike=22900.0,
        width=100.0,
        expiry=entry_day,
        lots=1,
        lot_size=lot_size,
        entry_credit=sold_entry - long_entry,
        exit_debit=(sold_exit - long_exit) if closed else None,
        pnl=0.0,
        margin=None,
        exit_class="unknown",
        sold_entry=sold_entry,
        long_entry=long_entry,
        sold_exit=sold_exit if closed else None,
        long_exit=long_exit if closed else None,
    )


def row(net, when, net_2x=None):
    return {
        "entry_time": when,
        "net": net,
        "net_2x": net - 10 if net_2x is None else net_2x,
        "unseen": False,
    }


def summary(trades, net, net_2x, drawdown, worst_day):
    return {
        "trades": trades,
        "net": net,
        "net_2x": net_2x,
        "drawdown": drawdown,
        "worst_day": worst_day,
    }


# ---- arithmetic -------------------------------------------------------------------------


def test_net_one_lot_matches_hand_computed_example():
    trade = make_trade(sold=(100.0, 30.0), long=(40.0, 10.0), lot_size=50)
    day = pd.Timestamp("2026-09-07")
    # Sold leg: 100 to 30. Bought leg: 40 to 10. Spread credit 60, debit 20, gross 40 points.
    gross_rupees = 40 * 50
    cost = leg_cost(-1, 100.0, 30.0, day, day, 50) + leg_cost(1, 40.0, 10.0, day, day, 50)
    assert cost > 0
    assert zf.cost_one_lot(trade) == pytest.approx(cost)
    assert zf.net_one_lot(trade) == pytest.approx(gross_rupees - cost)
    assert zf.net_one_lot(trade, 2.0) == pytest.approx(gross_rupees - 2 * cost)


def test_open_trade_has_no_net_or_cost():
    trade = make_trade(closed=False)
    assert zf.net_one_lot(trade) is None
    assert zf.cost_one_lot(trade) is None


def test_rows_for_keeps_closed_trades_and_filters_calls():
    trades = [
        make_trade("p1", date(2026, 9, 7), kind="PE"),
        make_trade("c1", date(2026, 9, 8), kind="CE"),
        make_trade("c2", date(2026, 9, 9), kind="CE", closed=False),
        make_trade("p2", date(2026, 9, 10), kind="PE"),
    ]
    all_rows = zf.rows_for(trades, "all")
    assert [r["advice_id"] for r in all_rows] == ["p1", "c1", "p2"]
    calls = zf.rows_for(trades, "calls")
    assert [r["advice_id"] for r in calls] == ["c1"]
    assert all(r["kind"] == "CE" for r in calls)
    assert calls[0]["unseen"] is False
    with pytest.raises(ValueError):
        zf.rows_for(trades, "puts")


def test_unseen_flag_follows_entry_date():
    trades = [make_trade("late", date(2026, 9, 24), kind="CE")]
    (row_,) = zf.rows_for(trades, "calls")
    assert row_["unseen"] is True


# ---- summary ----------------------------------------------------------------------------


def test_summarize_hand_computed_series_is_order_independent():
    rows = [
        row(-250, "2026-09-09T12:00:00+05:30"),
        row(100, "2026-09-07T10:00:00+05:30"),
        row(200, "2026-09-08T10:00:00+05:30"),
        row(-300, "2026-09-07T11:00:00+05:30"),
        row(-250, "2026-09-09T10:00:00+05:30"),
    ]
    s = zf.summarize(rows)
    assert s["trades"] == 5
    assert s["wins"] == 2
    assert s["win_rate"] == 0.4
    assert s["net"] == -500
    assert s["net_2x"] == -550
    assert s["mean"] == -100
    assert s["profit_factor"] == pytest.approx(0.375)
    assert s["average_win"] == 150
    assert s["average_loss"] == pytest.approx(-266.67)
    assert s["worst_trade"] == -300
    # Day totals: 7 Sep -200, 8 Sep +200, 9 Sep -500.
    assert s["worst_day"] == -500
    # Cumulative: 100, -200, 0, -250, -500. Peak 100 falls to -500: 600.
    assert s["drawdown"] == 600


def test_summarize_empty_is_safe():
    s = zf.summarize([])
    assert s["trades"] == 0
    assert s["net"] == 0
    assert s["drawdown"] == 0
    assert s["worst_day"] == 0
    assert s["win_rate"] is None
    assert s["profit_factor"] is None


# ---- gates ------------------------------------------------------------------------------


def test_gates_inconclusive_below_twenty_unseen_call_trades():
    calls = summary(19, 5000, 1000, 1000, -500)
    everything = summary(40, 9000, 5000, 30000, -9000)
    g = zf.gates(calls, everything)
    assert g["outcome"] == "inconclusive"
    assert g["trades_needed"] == 11
    assert "not claimed" in g["note"]


def test_gates_supported_when_all_five_pass():
    calls = summary(25, 5000, 1000, 10000, -5000)
    everything = summary(40, 9000, 5000, 30000, -9000)
    g = zf.gates(calls, everything)
    assert all(
        g[k]
        for k in (
            "g1_net_positive",
            "g2_net_2x_positive",
            "g3_drawdown_under_20000",
            "g4_worst_day_above_minus_10000",
            "g5_drawdown_below_zen_all",
        )
    )
    assert g["outcome"] == "supported"
    assert g["trades_needed"] == 5


def test_gates_unsupported_names_the_failing_gate():
    calls = summary(25, 5000, 1000, 25000, -5000)
    everything = summary(40, 9000, 5000, 30000, -9000)
    g = zf.gates(calls, everything)
    assert g["g3_drawdown_under_20000"] is False
    assert g["g5_drawdown_below_zen_all"] is True
    assert g["outcome"] == "unsupported"


def test_gates_worst_day_must_be_above_minus_ten_thousand():
    calls = summary(25, 5000, 1000, 10000, -10000)
    everything = summary(40, 9000, 5000, 30000, -9000)
    g = zf.gates(calls, everything)
    assert g["g4_worst_day_above_minus_10000"] is False
    assert g["outcome"] == "unsupported"


# ---- report -----------------------------------------------------------------------------


def test_report_counts_seen_unseen_and_open():
    trades = [
        make_trade("early", date(2026, 9, 7), kind="PE"),
        make_trade("late", date(2026, 9, 25), kind="CE"),
        make_trade("open", date(2026, 9, 26), kind="CE", closed=False),
    ]
    rep = zf.report(trades, 2.0)
    assert rep["seen"]["all"]["trades"] == 1
    assert rep["unseen"]["all"]["trades"] == 1
    assert rep["unseen"]["calls"]["trades"] == 1
    assert rep["open_trades"] == 1
    assert rep["latest_entry"] == trades[2].entry_time.isoformat()
    assert rep["stale_warning"] is None


def test_report_warns_when_file_is_stale():
    trades = [make_trade("late", date(2026, 9, 25), kind="CE")]
    rep = zf.report(trades, 12.4)
    assert rep["stale_warning"] == "The Zen trade file is 12 days old. Ask for a fresh download."


def test_report_warns_when_no_unseen_trades():
    trades = [make_trade("early", date(2026, 9, 7))]
    rep = zf.report(trades, 1.0)
    assert rep["stale_warning"] == "No Zen trades after 23 Sep 2026 are in the file yet."


def test_report_joins_both_warnings():
    trades = [make_trade("early", date(2026, 9, 7))]
    rep = zf.report(trades, 30.0)
    assert "30 days old" in rep["stale_warning"]
    assert "No Zen trades after 23 Sep 2026" in rep["stale_warning"]


def test_report_unknown_age_gives_no_stale_warning_when_unseen_exists():
    trades = [make_trade("late", date(2026, 9, 25), kind="CE")]
    assert zf.report(trades, None)["stale_warning"] is None


def test_report_empty_list_is_safe():
    rep = zf.report([], None)
    assert rep["latest_entry"] is None
    assert rep["gates"]["outcome"] == "inconclusive"
    assert "No Zen trades" in rep["stale_warning"]


# ---- script -----------------------------------------------------------------------------


def load_script():
    spec = importlib.util.spec_from_file_location("run_zen_follow", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def zen_record(advice_id, created, kind, sold_strike, long_strike, sold, long):
    """A published executed credit spread in the shape load_trades reads. sold and long are (entry, exit)."""
    sold_symbol = f"NIFTY26907{sold_strike}{kind}"
    long_symbol = f"NIFTY26907{long_strike}{kind}"
    return {
        "_id": advice_id,
        "executionState": "EXECUTED",
        "createdAt": created,
        "closedOn": "2026-09-07T09:30:00Z",
        "pnl": 0,
        "summary": [{"title": "Target hit", "lotsTraded": 1}],
        "trades": [
            {
                "transactionType": "SELL",
                "symbol": sold_symbol,
                "entryPrice": sold[0],
                "avgExitPrice": sold[1],
                "multiplier": 50,
            },
            {
                "transactionType": "BUY",
                "symbol": long_symbol,
                "entryPrice": long[0],
                "avgExitPrice": long[1],
                "multiplier": 50,
            },
        ],
    }


def write_advices(path, records):
    path.write_text(json.dumps({"success": True, "pastAdvices": records}), encoding="utf-8")


def test_script_writes_report_and_csvs_under_working_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "zen.json"
    put = zen_record("p1", "2026-09-07T04:30:00Z", "PE", 23000, 22900, (100, 30), (40, 10))
    call = zen_record("c1", "2026-09-08T04:30:00Z", "CE", 23500, 23600, (80, 60), (30, 20))
    write_advices(source, [put, call])

    assert load_script().main([str(source)]) == 0

    out = tmp_path / "db" / "zen_follow"
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["seen"]["all"]["trades"] == 2
    assert report["seen"]["calls"]["trades"] == 1
    assert report["unseen"]["all"]["trades"] == 0
    assert "No Zen trades after 23 Sep 2026" in report["stale_warning"]
    assert (out / "trades_all.csv").read_text(encoding="utf-8").count("\n") == 3
    assert (out / "trades_calls.csv").read_text(encoding="utf-8").count("\n") == 2
    assert "Outcome: inconclusive" in capsys.readouterr().out


def test_script_missing_file_exits_zero_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert load_script().main([str(tmp_path / "missing.json")]) == 0
    assert "No Zen trade file" in capsys.readouterr().out
    assert not (tmp_path / "db").exists()


def test_script_reads_path_from_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ZEN_ADVICES_FILE", str(tmp_path / "missing.json"))
    assert load_script().main([]) == 0
    assert "No Zen trade file" in capsys.readouterr().out


def test_script_unreadable_file_returns_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "zen.json"
    source.write_text("not json", encoding="utf-8")
    assert load_script().main([str(source)]) == 1
    assert not (tmp_path / "db").exists()
