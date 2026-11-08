"""The forward tests list also shows the Zen shadow follow ledger and the ETF trend ledgers."""

import json

from services.algos import agent_view


def _zen_report(tmp_path):
    report = {
        "unseen": {"all": {"trades": 8, "net": -458.4}, "calls": {"trades": 6, "net": 5501.2}},
        "gates": {"outcome": "inconclusive", "trades_needed": 24},
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_the_zen_ledger_gives_a_benchmark_row_and_a_candidate_row_with_its_verdict(tmp_path):
    rows = agent_view._zen_rows(_zen_report(tmp_path))
    assert [r["name"].split(" (")[0] for r in rows] == [
        "Zen all advices, followed at one lot",
        "Zen call spreads only",
    ]
    assert rows[0]["completed"] == 8 and rows[0]["net"] == -458
    assert (
        rows[1]["verdict"] == "inconclusive"
        and rows[1]["trades_to_go"] == 24
        and rows[1]["net"] == 5501
    )


def test_a_missing_or_broken_zen_report_gives_no_rows(tmp_path):
    assert agent_view._zen_rows(tmp_path / "absent.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert agent_view._zen_rows(bad) == []


def test_the_etf_trend_ledgers_show_sessions_and_net_and_ignore_duplicate_nights(tmp_path):
    lines = [
        "session,nav",
        "2026-11-02,100000.0",
        "2026-11-03,100250.0",
        "2026-11-03,100250.0",
        "2026-11-04,99900.0",
    ]
    (tmp_path / "c01_trend200_base.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows = agent_view._etf_trend_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["completed"] == 3 and rows[0]["net"] == -100
    assert "ETF trend" in rows[0]["name"]


def test_forward_status_includes_both_when_the_files_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGO_ZEN_FOLLOW_REPORT", str(_zen_report(tmp_path)))
    (tmp_path / "etf").mkdir()
    (tmp_path / "etf" / "c02_cross50_200_base.csv").write_text(
        "session,nav\n2026-11-02,100000\n", encoding="utf-8"
    )
    monkeypatch.setenv("ALGO_ETF_LEDGER_DIR", str(tmp_path / "etf"))
    monkeypatch.setenv("ALGO_FORWARD_S3N_REPORT", str(tmp_path / "none.json"))
    monkeypatch.setenv("ALGO_FORWARD_C1_CSV", str(tmp_path / "none.csv"))
    monkeypatch.setenv("ALGO_FORWARD_EOD_DIR", str(tmp_path / "none"))
    monkeypatch.setenv("ALGO_REGISTRY_DIR", str(tmp_path / "reg"))
    names = [r["name"] for r in agent_view.forward_status()]
    assert any(n.startswith("Zen call spreads only") for n in names)
    assert any(n.startswith("ETF trend") for n in names)
