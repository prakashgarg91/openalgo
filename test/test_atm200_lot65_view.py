"""Synthetic checks that the lot-65 view sizes every trade and cost at 65, whatever the expiry.

No real data is read: a tiny repo (MANIFEST.csv, one-minute index, a VIX file and one 5-minute
candle tar per expiry) is built under tmp_path for expiries whose real nse_lots lot is 25 or 75,
and the lot actually handed to replay_trade and eod_screen.leg_cost is recorded.
"""

import io
import tarfile

import pandas as pd

import scripts.algo_backtest.atm200_lot65_view as view
from services.algos import nse_lots

SPOT = 24503.0  # atm_strike rounds this to 24500; the bought call is 200 points higher
SOLD_K, LONG_K = 24500, 24700
# One expiry per lot era in the data repo: the 25 era, the kept-old-lot 25 monthly, and the 75 era.
CASES = {"2024-11-28": 25, "2025-01-30": 25, "2025-03-27": 75}


def _synthetic_repo(root):
    (root / "context" / "daily").mkdir(parents=True)
    (root / "index").mkdir()
    (root / "bars5m").mkdir()
    (root / "context" / "daily" / "_INDIAVIX.csv").write_text(
        ",close\n2024-11-01,13.2\n", encoding="utf-8"
    )
    idx_rows = ["timestamp,close"]
    for expiry in CASES:
        day = pd.Timestamp(expiry) - pd.Timedelta(days=1)  # the entry session, one day before
        idx_rows.append(f"{day:%Y-%m-%d} 10:15:00,{SPOT}")
        idx_rows.append(f"{pd.Timestamp(expiry):%Y-%m-%d} 15:00:00,{SPOT}")
        # Four 5-minute bars from 10:15: the entry closes give an 80-point credit, later bars 20.
        stamps = pd.date_range(f"{day:%Y-%m-%d} 10:15:00", periods=4, freq="5min")
        legs = {
            ("CE", SOLD_K): [(200, 202, 198, 200)] + [(130, 132, 128, 130)] * 3,
            ("CE", LONG_K): [(120, 122, 118, 120)] + [(110, 112, 108, 110)] * 3,
        }
        with tarfile.open(root / "bars5m" / f"{expiry}.tar.gz", "w:gz") as tar:
            for (kind, strike), rows in legs.items():
                text = "timestamp,open,high,low,close\n" + "".join(
                    f"{ts:%Y-%m-%d %H:%M:%S},{o},{h},{lo},{c}\n"
                    for ts, (o, h, lo, c) in zip(stamps, rows, strict=False)
                )
                data = text.encode()
                info = tarfile.TarInfo(f"{expiry}_{kind}_{strike}.csv")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    (root / "index" / "nifty_1m.csv").write_text("\n".join(idx_rows) + "\n", encoding="utf-8")
    manifest = ["expiry,contracts,rows,stored_on"] + [f"{e},2,8,2026-11-26" for e in CASES]
    (root / "MANIFEST.csv").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    return root


def test_every_trade_and_cost_uses_lot_65_whatever_the_expiry(tmp_path, monkeypatch):
    repo = _synthetic_repo(tmp_path)
    for expiry, real_lot in CASES.items():
        assert (
            nse_lots.nifty_lot(pd.Timestamp(expiry)) == real_lot
        )  # not 65: the view must override
    replay_lots, cost_lots = [], []
    real_replay, real_cost = view.replay_trade, view.es.leg_cost

    def recording_replay(sold, long_, entry_ts, end_ts, gate_credit, variant, lot=view.LOT):
        replay_lots.append(lot)
        return real_replay(sold, long_, entry_ts, end_ts, gate_credit, variant, lot)

    def recording_cost(side, entry, exit_, entry_day, exit_day, lot):
        cost_lots.append(lot)
        return real_cost(side, entry, exit_, entry_day, exit_day, lot)

    monkeypatch.setattr(view, "replay_trade", recording_replay)
    monkeypatch.setattr(view.es, "leg_cost", recording_cost)

    frames = view.run(repo)

    assert set(frames) == set(view.VARIANTS)
    trades_per_variant = len(CASES)
    for name, frame in frames.items():
        assert len(frame) == trades_per_variant, name  # no expiry dropped for its lot
        expected_gross = (frame["credit"] - frame["exit"]) * 65
        assert (frame["gross"] - expected_gross).abs().max() < 1e-9, name
    assert replay_lots == [65] * (len(view.VARIANTS) * trades_per_variant)
    assert cost_lots == [65] * (2 * len(view.VARIANTS) * trades_per_variant)


def test_the_lot_is_still_65_where_nifty_lot_would_not_guess_one():
    # Before the first documented circular nifty_lot returns None rather than guess; the view has
    # its own constant, so it does not depend on that table at all.
    assert nse_lots.nifty_lot(pd.Timestamp("2020-08-27")) is None
    assert view.LOT == 65
