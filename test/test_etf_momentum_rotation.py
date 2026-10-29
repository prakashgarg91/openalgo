"""The rotation script must decide exactly what the tested rule decides, and place nothing by accident."""

import importlib.util
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services.algos import universe as u

SPEC = importlib.util.spec_from_file_location(
    "etf_rotation",
    Path(__file__).resolve().parents[1] / "strategies/examples/etf_momentum_rotation.py",
)
rot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rot)  # importing must not need an API key or the network


def bars(days=900, seed=2):
    idx = pd.bdate_range("2019-01-01", periods=days)
    out = {}
    for key, s in (("equity", seed), ("gold", seed + 9)):
        r = np.random.default_rng(s).normal(0.0004, 0.01, days)
        close = 100 * np.exp(np.cumsum(r))
        out[key] = pd.DataFrame({"Open": close, "Close": close}, index=idx)
    return out


@pytest.mark.parametrize(
    ("lookback", "mode"), [(63, "best"), (126, "best"), (126, "all"), (252, "all")]
)
def test_the_script_holds_exactly_what_the_tested_rule_holds(lookback, mode):
    b = bars()
    held = u.held_dual_momentum(b, lookback, mode)
    eq, gd = b["equity"]["Close"], b["gold"]["Close"]
    idx = eq.index
    checked = 0
    for i in range(lookback + 2, len(idx) - 1):
        month_end_yesterday = idx[i - 1].month != idx[i].month
        if not month_end_yesterday:
            continue
        # The script runs on day i, the first trading day of the month, with closes through day i-1.
        weights = rot.signal_weights(list(eq.iloc[:i]), list(gd.iloc[:i]), lookback, mode)
        assert weights[rot.EQUITY] == pytest.approx(held["equity"].iloc[i])
        assert weights[rot.GOLD] == pytest.approx(held["gold"].iloc[i])
        assert rot.is_first_trading_day_of_month(idx[i - 1].date(), idx[i].date())
        checked += 1
    assert checked > 10


def test_it_is_in_cash_when_neither_etf_rose_and_when_there_is_too_little_history():
    down = [100.0 - i * 0.1 for i in range(200)]
    assert rot.signal_weights(down, down, 126) == {rot.EQUITY: 0.0, rot.GOLD: 0.0}
    assert rot.signal_weights(down[:50], down[:50], 126) == {rot.EQUITY: 0.0, rot.GOLD: 0.0}


def test_it_picks_the_one_that_rose_most_or_splits_among_those_that_rose():
    up_more = [100.0 + i * 0.5 for i in range(200)]
    up_less = [100.0 + i * 0.1 for i in range(200)]
    assert rot.signal_weights(up_more, up_less, 126, "best") == {rot.EQUITY: 1.0, rot.GOLD: 0.0}
    assert rot.signal_weights(up_less, up_more, 126, "best") == {rot.EQUITY: 0.0, rot.GOLD: 1.0}
    assert rot.signal_weights(up_more, up_less, 126, "all") == {rot.EQUITY: 0.5, rot.GOLD: 0.5}


def test_it_acts_only_on_the_first_trading_day_of_a_new_month():
    assert rot.is_first_trading_day_of_month(date(2026, 9, 30), date(2026, 10, 1))
    assert rot.is_first_trading_day_of_month(
        date(2026, 10, 30), date(2026, 11, 2)
    )  # over a weekend
    assert not rot.is_first_trading_day_of_month(date(2026, 10, 1), date(2026, 10, 2))
    assert rot.is_first_trading_day_of_month(date(2025, 12, 31), date(2026, 1, 1))  # across a year


def test_orders_sell_first_and_never_sell_what_it_does_not_hold():
    prices = {rot.EQUITY: 250.0, rot.GOLD: 100.0}
    orders = rot.plan_orders({rot.EQUITY: 100}, {rot.EQUITY: 0.0, rot.GOLD: 1.0}, prices, 100_000)
    assert orders == [("SELL", rot.EQUITY, 100), ("BUY", rot.GOLD, 1000)]
    assert rot.plan_orders({}, {rot.EQUITY: 0.0, rot.GOLD: 0.0}, prices, 100_000) == []
    assert (
        rot.plan_orders({rot.GOLD: 1000}, {rot.EQUITY: 0.0, rot.GOLD: 1.0}, prices, 100_000) == []
    )


def test_it_buys_whole_shares_and_never_more_than_the_capital():
    qty = rot.plan_orders(
        {}, {rot.EQUITY: 1.0, rot.GOLD: 0.0}, {rot.EQUITY: 257.3, rot.GOLD: 1.0}, 100_000
    )[0][2]
    assert qty == 388 and qty * 257.3 <= 100_000


def test_a_zero_price_cannot_cause_a_buy():
    assert (
        rot.plan_orders(
            {}, {rot.EQUITY: 1.0, rot.GOLD: 0.0}, {rot.EQUITY: 0.0, rot.GOLD: 1.0}, 100_000
        )
        == []
    )


def test_state_is_saved_whole_and_a_damaged_file_means_nothing_held(tmp_path):
    path = tmp_path / "state" / "rot.json"
    assert rot.load_state(path) == {"book": {}, "last_rebalanced": None}
    rot.save_state(path, {"book": {"GOLDBEES": 10}, "last_rebalanced": "2026-10"})
    assert rot.load_state(path)["book"] == {"GOLDBEES": 10}
    path.write_text("{broken")
    assert rot.load_state(path) == {"book": {}, "last_rebalanced": None}


# -- main(), with a fake broker client ------------------------------------------------------------------


class FakeClient:
    instances = []

    def __init__(self, **kwargs):
        self.orders = []
        self.accept = True
        FakeClient.instances.append(self)

    def history(self, *, symbol, exchange, interval, start_date, end_date):
        idx = pd.bdate_range(
            end="2026-11-02", periods=400
        )  # includes the still-forming bar for today
        base = 100.0 if symbol == rot.EQUITY else 50.0
        slope = 0.05 if symbol == rot.GOLD else -0.01  # gold rising, equity falling
        return pd.DataFrame({"close": [base + i * slope for i in range(len(idx))]}, index=idx)

    def quotes(self, *, symbol, exchange):
        return {"status": "success", "data": {"ltp": 250.0 if symbol == rot.EQUITY else 70.0}}

    def placeorder(self, **kwargs):
        self.orders.append(kwargs)
        return {"status": "success" if self.accept else "error"}


@pytest.fixture
def harness(monkeypatch, tmp_path):
    import sys
    import types
    from datetime import datetime as real_datetime

    FakeClient.instances.clear()
    fake_module = types.SimpleNamespace(api=FakeClient)
    monkeypatch.setitem(sys.modules, "openalgo", fake_module)

    class Fixed(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(
                2026, 11, 2, 15, 16, tzinfo=rot.IST
            )  # first trading day of November

    monkeypatch.setattr(rot, "datetime", Fixed)
    monkeypatch.setattr(rot, "_wait_until", lambda hhmm: None)
    monkeypatch.setenv("OPENALGO_API_KEY", "key")
    monkeypatch.setenv("ETF_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.delenv("DRY_RUN", raising=False)
    return tmp_path / "state.json"


def test_it_will_not_start_without_an_api_key(harness, monkeypatch, capsys):
    monkeypatch.delenv("OPENALGO_API_KEY")
    assert rot.main() == 1 and "No OpenAlgo API key" in capsys.readouterr().out


def test_by_default_it_only_says_what_it_would_do(harness, capsys):
    assert rot.main() == 0
    client = FakeClient.instances[0]
    assert client.orders == [] and "DRY RUN: would BUY" in capsys.readouterr().out
    assert not harness.exists()  # nothing recorded, because nothing was bought


def test_a_live_run_buys_the_rising_etf_with_delivery_orders_and_records_it(harness, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    assert rot.main() == 0
    (order,) = FakeClient.instances[0].orders
    assert order["symbol"] == rot.GOLD and order["action"] == "BUY" and order["product"] == "CNC"
    assert order["quantity"] == int(100_000 // 70.0) and order["exchange"] == "NSE"
    assert rot.load_state(harness) == {"book": {rot.GOLD: 1428}, "last_rebalanced": "2026-11"}


def test_a_second_run_in_the_same_month_does_nothing(harness, monkeypatch, capsys):
    monkeypatch.setenv("DRY_RUN", "false")
    rot.main()
    capsys.readouterr()
    assert rot.main() == 0
    assert (
        len(FakeClient.instances[1].orders) == 0
        and "already done this month" in capsys.readouterr().out
    )


def test_a_rejected_order_is_not_recorded_as_done(harness, monkeypatch, capsys):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr(FakeClient, "placeorder", lambda self, **kw: {"status": "error"})
    assert rot.main() == 1
    assert "was not accepted" in capsys.readouterr().out
    assert not harness.exists()


def test_it_does_nothing_in_the_middle_of_a_month(harness, monkeypatch, capsys):
    from datetime import datetime as real_datetime

    class Mid(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 11, 3, 15, 16, tzinfo=rot.IST)

    monkeypatch.setattr(rot, "datetime", Mid)

    def history(self, **kw):
        idx = pd.bdate_range(end="2026-11-03", periods=400)
        return pd.DataFrame({"close": np.linspace(100, 120, 400)}, index=idx)

    monkeypatch.setattr(FakeClient, "history", history)
    monkeypatch.setenv("DRY_RUN", "false")
    assert rot.main() == 0
    assert FakeClient.instances[0].orders == [] and "Nothing to do" in capsys.readouterr().out


# -- trend and hold modes, and the state kept after a partial rebalance -----------------------------------


@pytest.mark.parametrize("n", [50, 100, 200])
def test_trend_mode_holds_exactly_what_the_tested_trend_rule_holds(n):
    b = bars(days=700, seed=5)
    held = u.held_trend(b, n)
    eq, gd = b["equity"]["Close"], b["gold"]["Close"]
    checked = 0
    for i in range(n + 2, len(eq) - 1):
        weights = rot.signal_weights(list(eq.iloc[:i]), list(gd.iloc[:i]), n, "trend")
        assert weights[rot.EQUITY] == pytest.approx(held["equity"].iloc[i])
        assert weights[rot.GOLD] == 0.0
        checked += 1
    assert checked > 100


def test_hold_mode_is_half_and_half_and_an_unknown_mode_is_refused():
    series = [100.0 + i * 0.1 for i in range(200)]
    assert rot.signal_weights(series, series, 126, "hold") == {rot.EQUITY: 0.5, rot.GOLD: 0.5}
    with pytest.raises(ValueError):
        rot.signal_weights(series, series, 126, "gold only")


def test_trend_mode_acts_every_trading_day_and_not_twice_in_one_day(harness, monkeypatch, capsys):
    from datetime import datetime as real_datetime

    class Mid(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(
                2026, 11, 3, 15, 16, tzinfo=rot.IST
            )  # a day that is not a month start

    monkeypatch.setattr(rot, "datetime", Mid)
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("ETF_MODE", "trend")
    monkeypatch.setenv("ETF_LOOKBACK", "100")

    def history(self, *, symbol, **kw):
        idx = pd.bdate_range(end="2026-11-03", periods=400)
        return pd.DataFrame(
            {"close": np.linspace(100, 160, 400)}, index=idx
        )  # rising: above its average

    monkeypatch.setattr(FakeClient, "history", history)
    assert rot.main() == 0
    (order,) = FakeClient.instances[0].orders
    assert (
        order["symbol"] == rot.EQUITY
        and order["action"] == "BUY"
        and order["strategy"] == "ETF rotation trend"
    )
    assert rot.load_state(harness)["last_rebalanced"] == "2026-11-03"
    capsys.readouterr()
    assert rot.main() == 0
    assert "already done today" in capsys.readouterr().out and not FakeClient.instances[1].orders


def test_a_refused_buy_after_a_sell_keeps_the_record_true(harness, monkeypatch, capsys):
    monkeypatch.setenv("DRY_RUN", "false")
    rot.save_state(harness, {"book": {rot.EQUITY: 100}, "last_rebalanced": "2026-10"})
    calls = []

    def place(self, **kw):
        calls.append(kw["action"])
        return {"status": "success" if kw["action"] == "SELL" else "error"}

    monkeypatch.setattr(FakeClient, "placeorder", place)
    assert rot.main() == 1
    assert calls == ["SELL", "BUY"]
    state = rot.load_state(harness)
    assert state["book"].get(rot.EQUITY, 0) == 0  # the sell went through and is recorded
    assert state["last_rebalanced"] == "2026-10"  # the month is not marked finished
    out = capsys.readouterr().out
    assert "price now against the last finished close" in out
