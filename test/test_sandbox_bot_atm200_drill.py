"""Isolated ATM 200 Sandbox drill-mode behavior using the existing fake API."""

import pytest
import test_algos_sandbox_bot_atm200 as atm_test

from scripts.algo_backtest import record_account
from services.algos import sandbox_bot as sb
from services.algos import sandbox_bot_atm200 as atm


def drill_bot(root, api, strike_offset=300):
    return atm.ATM200Bot(
        api,
        root / "db" / "sandbox_bot_atm200_drill" / "state.json",
        root / "db" / "sandbox_bot_atm200_drill" / "trades.csv",
        notify=lambda _: None,
        wait=10,
        strategy="ATM200-drill",
        alert_prefix="Sandbox DRILL:",
        strike_offset=strike_offset,
    )


@pytest.mark.parametrize(
    ("offset", "sold_strike", "bought_strike"), [(300, 25300, 25500), (0, 25000, 25200)]
)
def test_drill_strike_offset_shifts_both_legs(tmp_path, offset, sold_strike, bought_strike):
    api = atm_test.FakeApi()
    sold = sb.contract_symbol(atm_test.EXPIRY, sold_strike)
    long = sb.contract_symbol(atm_test.EXPIRY, bought_strike)
    api.ltp.update({sold: 20.0, long: 6.0})
    api.quotes.update({sold: (19.5, 20.5), long: (5.5, 6.0)})

    bot = drill_bot(tmp_path, api, offset) if offset else atm_test.bot(tmp_path, api)
    state = bot.enter_spread(atm_test.EXPIRY, atm_test.NOW, set(), atm_test.FRESH_VIX)

    assert state["sold"] == sold and state["long"] == long
    assert [(order["action"], order["symbol"]) for order in atm_test.placed(api)] == [
        ("BUY", long),
        ("SELL", sold),
    ]


def test_drill_orders_use_the_drill_strategy_and_sandbox_state_path(tmp_path):
    api = atm_test.FakeApi()
    sold = sb.contract_symbol(atm_test.EXPIRY, 25300)
    long = sb.contract_symbol(atm_test.EXPIRY, 25500)
    api.ltp.update({sold: 20.0, long: 6.0})
    api.quotes.update({sold: (19.5, 20.5), long: (5.5, 6.0)})
    bot = drill_bot(tmp_path, api)

    bot.enter_spread(atm_test.EXPIRY, atm_test.NOW, set(), atm_test.FRESH_VIX)

    orders = atm_test.placed(api)
    assert all(order["strategy"] == "ATM200-drill" for order in orders)
    assert all(order["sandbox_only"] is True for order in orders)
    state_path = tmp_path / "db" / "sandbox_bot_atm200_drill" / "state.json"
    assert state_path.is_file()
    assert bot.state()["sold"] == sold
    assert not (tmp_path / "db" / "state.json").exists()


@pytest.mark.parametrize("timestamp", ["2020-01-01 00:00:00", "2035-12-31 23:59:59"])
def test_drill_strategy_is_always_a_rehearsal(timestamp):
    assert record_account.is_rehearsal("ATM200-drill", timestamp)
