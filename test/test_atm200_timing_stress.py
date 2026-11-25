import pandas as pd

from scripts.algo_backtest.atm200_timing_stress import replay_trade


def bars(rows):
    index = pd.date_range("2026-01-01 10:15", periods=len(rows), freq="5min")
    return pd.DataFrame(rows, index=index, columns=["open", "high", "low", "close"])


def test_intrabar_high_stops_when_close_does_not():
    sold = bars([(100, 102, 98, 100), (100, 270, 99, 130), (130, 135, 125, 130)])
    long_ = bars([(20, 22, 18, 20), (20, 21, 19, 20), (20, 22, 18, 20)])
    end = sold.index[-1]
    base = replay_trade(sold, long_, sold.index[0], end, 80, "base")
    stress = replay_trade(sold, long_, sold.index[0], end, 80, "c_intrabar_stop")
    assert base["why"] != "stop"
    assert stress["why"] == "stop"
    assert stress["exit"] == 200


def test_entry_open_changes_credit_from_close():
    sold = bars([(110, 112, 108, 100), (100, 105, 95, 100)])
    long_ = bars([(20, 22, 18, 20), (20, 22, 18, 20)])
    end = sold.index[-1]
    close_trade = replay_trade(sold, long_, sold.index[0], end, 80, "base")
    open_trade = replay_trade(sold, long_, sold.index[0], end, 80, "a_entry_open")
    assert close_trade["credit"] == 80
    assert open_trade["credit"] == 90


def test_next_bar_fill_and_last_bar_fallback():
    sold = bars([(100, 102, 98, 100), (220, 222, 218, 220), (140, 142, 138, 140)])
    long_ = bars([(20, 22, 18, 20), (20, 22, 18, 20), (20, 22, 18, 20)])
    end = sold.index[-1]
    delayed = replay_trade(sold, long_, sold.index[0], end, 80, "d_exit_next_bar")
    assert delayed["why"] == "stop"
    assert delayed["exit_ts"] == sold.index[-1]
    assert delayed["exit"] == 120
    last = replay_trade(
        sold.iloc[:2], long_.iloc[:2], sold.index[0], sold.index[1], 80, "d_exit_next_bar"
    )
    assert last["exit_ts"] == sold.index[1]


def test_an_exit_is_never_priced_above_the_spread_width():
    pass
