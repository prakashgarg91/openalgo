"""The debugger must agree with the Lab it replays, and explain a skip by its real cause."""

import pytest
from test_algos_lab import history  # noqa: F401  (fixture)

from services.algos import debugger, lab


def _first_days(history_, algo_id):
    full = lab.run_lab(history_, algo_id)
    traded = {t["date"] for t in full.trades}
    nifty_days = [d.strftime("%Y-%m-%d") for d in history_.frames["nifty"].index[40:-2]]
    skipped = [d for d in nifty_days if d not in traded]
    return full, sorted(traded), skipped


def test_a_traded_day_matches_the_lab_to_the_rupee(history):  # noqa: F811
    full, traded, _ = _first_days(history, "zen")
    assert traded, "fixture should produce at least one trade"
    day = traded[0]
    out = debugger.run(history, "zen", day)
    lab_pnl = next(t["pnl"] for t in full.trades if t["date"] == day)
    assert f"{lab_pnl:,.0f}" in out["verdict"]
    assert out["steps"][-1]["status"] == "info" and "model" in out["steps"][-1]["detail"].lower()
    assert [s["status"] for s in out["steps"] if s["title"] == "The trade"] == ["pass"]


def test_a_skipped_day_names_the_step_that_stopped_it(history):  # noqa: F811
    _, _, skipped = _first_days(history, "calm_condor")
    assert skipped
    out = debugger.run(history, "calm_condor", skipped[0])
    stops = [s for s in out["steps"] if s["status"] == "stop"]
    assert stops and out["verdict"].startswith("Calm Condor sat out")
    assert all(s["title"] and s["detail"] for s in out["steps"])


def test_a_day_that_cannot_be_replayed_is_explained(history):  # noqa: F811
    for bad in ("2024-01-06", "1999-01-01", "2030-01-02"):
        with pytest.raises(debugger.DayUnavailable) as exc:
            debugger.run(history, "zen", bad)
        assert "cannot be replayed" in str(exc.value)


def test_recorded_decisions_are_explained_in_words():
    skip = debugger.explain_recorded(
        {
            "action": "skip",
            "regime_label": "volatile",
            "bias": "neutral",
            "confidence": 0.9,
            "reason": "Volatile market.",
        },
        "Zen",
    )
    assert skip["verdict"].startswith("Zen sat out") and skip["steps"][-1]["status"] == "stop"
    trade = debugger.explain_recorded(
        {
            "action": "trade",
            "regime_label": "calm",
            "bias": "bullish",
            "confidence": 1,
            "side": "bull_put",
            "lots": 4,
            "max_loss_inr": 45000,
            "reason": "ok",
        },
        "Zen",
    )
    assert "bull put" in trade["steps"][-1]["detail"] and "45,000" in trade["steps"][-1]["detail"]
