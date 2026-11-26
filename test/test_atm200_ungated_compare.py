"""Synthetic-repo tests: the ungated ATM 200 replay takes the days the gated rule refuses.

The repo built here has one expiry (Thursday 2026-01-08, lot 65), three evaluable days and a
flat 80-point spread at every bar, so a day's presence in a replay's output depends only on
the entry gates, not on the exits.
"""

import io
import tarfile

import pandas as pd

from scripts.algo_backtest.atm200_timing_stress import replay_trade as gated_replay
from scripts.algo_backtest.atm200_timing_stress import run as gated_run
from scripts.algo_backtest.atm200_ungated_compare import replay_trade_ungated, run_ungated

EXPIRY = "2026-01-08"
DAYS = ("2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08")
BAR_CLOCKS = ("10:15:00", "10:20:00", "15:00:00")
VIX_DAY = pd.Timestamp("2026-01-07")  # its previous session closed at VIX 25
CALM_DAYS = {pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-06")}


def bars(rows):
    index = pd.date_range("2026-01-01 10:15", periods=len(rows), freq="5min")
    return pd.DataFrame(rows, index=index, columns=["open", "high", "low", "close"])


def option_bars(constant, missing_day=None):
    rows = []
    for day in DAYS:
        for clock in BAR_CLOCKS:
            if day == missing_day:
                values = [float("nan")] * 4  # the bar exists but carries no price
            else:
                values = [constant, constant + 2, constant - 2, constant]
            rows.append(
                {
                    "timestamp": f"{day} {clock}",
                    **dict(zip(("open", "high", "low", "close"), values, strict=False)),
                }
            )
    return pd.DataFrame(rows)[["timestamp", "open", "high", "low", "close"]]


def make_repo(root, missing_price_day=None):
    repo = root / "data"
    (repo / "context" / "daily").mkdir(parents=True)
    (repo / "index").mkdir(parents=True)
    (repo / "bars5m").mkdir(parents=True)
    (repo / "MANIFEST.csv").write_text(f"expiry\n{EXPIRY}\n", encoding="utf-8")
    pd.DataFrame(
        {"timestamp": [f"{day} 10:15:00" for day in DAYS], "close": [25010.0] * len(DAYS)}
    ).to_csv(repo / "index" / "nifty_1m.csv", index=False)
    (repo / "context" / "daily" / "_INDIAVIX.csv").write_text(
        "timestamp,close\n2026-01-05 10:00:00+00:00,15.0\n2026-01-06 10:00:00+00:00,25.0\n",
        encoding="utf-8",
    )
    with tarfile.open(repo / "bars5m" / f"{EXPIRY}.tar.gz", "w:gz") as tar:
        for name, frame in (
            ("NIFTY_CE_25000.csv", option_bars(100.0, missing_price_day)),
            ("NIFTY_CE_25200.csv", option_bars(20.0)),
        ):
            payload = frame.to_csv(index=False).encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return repo


def test_vix25_day_is_skipped_by_the_gated_path_and_taken_by_the_ungated_path(tmp_path):
    repo = make_repo(tmp_path)
    gated = gated_run(repo)
    ungated = run_ungated(repo)
    for name in ("base", "e_all"):
        assert set(gated[name]["date"]) == CALM_DAYS
        assert set(ungated[name]["date"]) == CALM_DAYS | {VIX_DAY}
        row = ungated[name][ungated[name]["date"] == VIX_DAY].iloc[0]
        assert row["vix_prev"] == 25.0
        assert row["credit"] == 80.0


def test_replay_without_the_credit_floor_takes_a_small_credit_day():
    sold = bars([(100, 102, 98, 100), (99, 101, 97, 99)])
    long_ = bars([(96, 98, 94, 96), (95, 97, 93, 95)])
    end = sold.index[-1]
    assert gated_replay(sold, long_, sold.index[0], end, 4.0, "base") is None
    trade = replay_trade_ungated(sold, long_, sold.index[0], end, "base")
    assert trade is not None
    assert trade["credit"] == 4.0


def test_a_day_with_a_missing_price_is_skipped_by_both_paths(tmp_path):
    repo = make_repo(tmp_path, missing_price_day="2026-01-06")
    gated = gated_run(repo)
    ungated = run_ungated(repo)
    for name in ("base", "e_all"):
        assert set(gated[name]["date"]) == {pd.Timestamp("2026-01-05")}
        assert set(ungated[name]["date"]) == {pd.Timestamp("2026-01-05"), VIX_DAY}
