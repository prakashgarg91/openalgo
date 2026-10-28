"""The account rule: Rs 1,00,000 with at most Rs 20,000 lost in a day."""

from datetime import UTC, datetime, timedelta

import pytest

from database import algo_db
from database import strategy_module_db as sm_store
from services.algos import mandate, runner
from services.algos.context import RegimeResult
from services.algos.templates import build
from services.strategy_module import engine as sm_engine

M = mandate.ONE_LAKH


def test_one_lakh_with_a_twenty_thousand_cap_is_twenty_percent():
    assert M.capital == 100_000 and M.max_daily_loss == 20_000 and M.max_loss_pct == 20.0


def test_one_lot_of_a_150_point_spread_fits_and_two_do_not():
    assert M.lots(150, 75) == 1  # worst case 11,250
    assert M.lots(100, 75) == 2  # 7,500 each
    assert M.lots(300, 75) == 0  # 22,500 is over the cap


def test_a_silly_cap_is_clamped():
    assert mandate.Mandate(100_000, 90_000).max_loss_pct == 50.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("20000", 20000.0), (" 5000 ", 5000.0), ("", None), ("x", None), ("-5", None), ("0", None)],
)
def test_the_daily_cap_setting_is_read_safely(monkeypatch, raw, expected):
    monkeypatch.setenv("ALGO_MAX_DAILY_LOSS_INR", raw)
    assert mandate.daily_cap_from_env() == expected


def test_sizing_uses_the_cap_when_set_and_the_default_otherwise(monkeypatch):
    calm = RegimeResult("calm", "bullish", 0.1, 1.0, ("ok",), ())
    monkeypatch.delenv("ALGO_MAX_DAILY_LOSS_INR", raising=False)
    plan = build("zen", calm, capital=100_000, lot_size=75, days_to_expiry=4)
    assert plan.action == "skip" and "Capital is too small" in plan.reason  # 10 percent of 1 lakh
    monkeypatch.setenv("ALGO_MAX_DAILY_LOSS_INR", "20000")
    plan = build("zen", calm, capital=100_000, lot_size=75, days_to_expiry=4)
    assert plan.action == "trade" and plan.lots == 1 and plan.max_loss_inr == 11_250
    assert plan.max_loss_inr <= 20_000


def test_an_explicit_percent_still_wins(monkeypatch):
    monkeypatch.setenv("ALGO_MAX_DAILY_LOSS_INR", "20000")
    assert mandate.effective_pct(100_000, 10.0, 5.0) == 5.0
    assert mandate.effective_pct(100_000, 10.0) == 20.0


def test_simulation_tracks_equity_worst_day_drawdown_and_breaches():
    trades = [
        {"date": "2025-01-01", "pnl": 3000.0},
        {"date": "2025-01-02", "pnl": -11000.0},
        {"date": "2025-01-03", "pnl": 2000.0},
        {"date": "2025-01-04", "pnl": -25000.0},
    ]
    sim = mandate.simulate(trades, M)
    assert sim["final_equity"] == 100_000 + 3000 - 11000 + 2000 - 25000
    assert sim["worst_day"] == -25000.0 and sim["max_drawdown"] == -34000.0
    assert sim["cap_breaches"] == [{"date": "2025-01-04", "loss": 25000.0}]
    assert sim["within_daily_cap"] is False and sim["ruined"] is False


def test_simulation_sums_trades_on_one_day_and_scales_by_lots():
    sim = mandate.simulate(
        [{"date": "d1", "pnl": -6000.0}, {"date": "d1", "pnl": -6000.0}], M, lots=1
    )
    assert sim["worst_day"] == -12000.0 and sim["within_daily_cap"]
    assert mandate.simulate([{"date": "d1", "pnl": -6000.0}], M, lots=4)["cap_breaches"]


def test_ruin_is_reported():
    sim = mandate.simulate([{"date": f"d{i}", "pnl": -15000.0} for i in range(8)], M)
    assert sim["ruined"] is True


def test_nothing_traded_is_a_flat_account():
    sim = mandate.simulate([], M)
    assert sim["final_equity"] == 100_000 and sim["days_traded"] == 0 and sim["return_pct"] == 0


# -- the daily budget across algos, through the real runner ---------------------------

USER = "mandate_user"


@pytest.fixture
def env(monkeypatch):
    algo_db.init_db()
    sm_store.init_db()
    monkeypatch.setenv("ALGO_MAX_DAILY_LOSS_INR", "20000")
    monkeypatch.setattr(runner, "nifty_lot_size", lambda: 75)
    monkeypatch.setattr(runner, "days_to_expiry", lambda api_key, today=None: 4)
    monkeypatch.setattr(runner, "_api_key", lambda user: "key")
    monkeypatch.setattr(runner, "_is_holiday", lambda day: False)
    monkeypatch.setattr(
        runner,
        "current_regime",
        lambda key: (RegimeResult("calm", "neutral", 0.0, 1.0, ("ok",), ()), None),
    )
    monkeypatch.setattr(runner, "_sync_strategy_jobs", lambda *a, **k: None)
    started = []

    class Result:
        ok = True
        run_id = 1
        error = None

    monkeypatch.setattr(
        sm_engine,
        "start_run",
        lambda sid, uid, mode, trigger_source="manual", **kw: started.append(sid) or Result(),
    )
    _wipe()
    yield started
    _wipe()


def _wipe():
    for dep in algo_db.list_deployments(USER):
        algo_db.delete_deployment(dep["id"], USER)
    for row in sm_store.db_session.query(sm_store.SmStrategy).filter_by(user_id=USER).all():
        row.status = "stopped"
    sm_store.db_session.commit()
    for row in sm_store.db_session.query(sm_store.SmStrategy).filter_by(user_id=USER).all():
        sm_store.delete_strategy(row.id, USER)
    algo_db.db_session.remove()
    sm_store.db_session.remove()


def _deploy(algo):
    dep, err = runner.deploy(USER, algo, 100_000)
    assert err is None, err
    algo_db.update_deployment(dep["id"], USER, active=True, mode="sandbox")
    return dep


def _today():
    return (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date()


def test_one_lakh_deploys_and_trades_one_lot_inside_the_cap(env):
    dep = _deploy("zen")
    out = runner.run_entry(dep["id"], today=_today())
    assert out["action"] == "trade" and out["lots"] == 1 and out["max_loss_inr"] == 11_250


def test_a_second_algo_that_would_pass_the_daily_cap_stands_aside_with_the_numbers(env):
    first, second = _deploy("zen"), _deploy("calm_condor")
    assert runner.run_entry(first["id"], today=_today())["action"] == "trade"
    out = runner.run_entry(second["id"], today=_today())
    assert out["action"] == "skip"
    assert "Rs 20,000" in out["reason"] and "Rs 11,250 is already at risk" in out["reason"]
    assert len(env) == 1  # the second never started


def test_yesterdays_risk_does_not_count_against_today(env):
    first, second = _deploy("zen"), _deploy("calm_condor")
    runner.run_entry(first["id"], today=_today())
    assert runner.committed_today(USER, _today() + timedelta(days=1)) == 0.0
    assert runner.run_entry(second["id"], today=_today() + timedelta(days=1))["action"] == "trade"
