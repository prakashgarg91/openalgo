"""Intraday replay engine and the Upstox expired-contract fetcher (no network, synthetic bars)."""

import sys
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest

from services.algos import intraday
from services.algos.intraday import OptionBars, Rules

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "algo_backtest"))
import fetch_upstox_expired as fetch  # noqa: E402

D1, D2, D3 = pd.Timestamp("2026-03-02"), pd.Timestamp("2026-03-03"), pd.Timestamp("2026-03-04")
EXPIRY = D3
STRIKES = list(range(23400, 24650, 50))


def tv(dist):
    return max(5.0, 130.0 - 0.25 * dist)


def px(strike, kind, spot):
    intrinsic = max(strike - spot, 0.0) if kind == "PE" else max(spot - strike, 0.0)
    return intrinsic + tv(abs(strike - spot))


def make_bars(days, spot_fn, strikes=STRIKES, expiry=EXPIRY, flat_bars=False):
    frames = {}
    for kind in ("CE", "PE"):
        for strike in strikes:
            parts = []
            for day in days:
                index = pd.date_range(
                    day + pd.Timedelta(hours=9, minutes=15),
                    day + pd.Timedelta(hours=15, minutes=25),
                    freq="5min",
                )
                o = np.array([px(strike, kind, spot_fn(ts)) for ts in index])
                step = pd.Timedelta(0) if flat_bars else pd.Timedelta(minutes=5)
                c = np.array([px(strike, kind, spot_fn(ts + step)) for ts in index])
                parts.append(
                    pd.DataFrame(
                        {
                            "open": o,
                            "high": np.maximum(o, c),
                            "low": np.minimum(o, c),
                            "close": c,
                            "volume": 100,
                            "oi": 1,
                        },
                        index=index,
                    )
                )
            frames[(expiry, kind, float(strike))] = pd.concat(parts)
    return OptionBars(frames)


def context(days, prev_close=24000.0, vix=12.0):
    return pd.DataFrame(
        {"prev_close": prev_close, "sma20": prev_close, "prev_vix": vix},
        index=pd.DatetimeIndex(days),
    )


def at(day, hhmm):
    h, m = hhmm.split(":")
    return day + pd.Timedelta(hours=int(h), minutes=int(m))


BASE = {"vix_ceiling": None, "gap_floor": None, "side_rule": "put"}


def test_spot_is_implied_from_put_call_parity():
    bars = make_bars([D1], lambda ts: 24012.0)
    assert bars.spot_at(EXPIRY, at(D1, "10:10")) == pytest.approx(24012.0, abs=0.01)


def test_spot_for_a_decision_ignores_the_bar_being_entered():
    calm = make_bars([D1], lambda ts: 24012.0)
    jump = make_bars([D1], lambda ts: 24012.0 if ts <= at(D1, "10:15") else 24300.0)
    # A bar is labelled by its start. The 10:10 bar closes at 10:15, the moment of the decision, so
    # it is known; the 10:15 bar is the one being entered and its close is not.
    assert calm.spot_at(EXPIRY, at(D1, "10:10")) == pytest.approx(
        jump.spot_at(EXPIRY, at(D1, "10:10")), abs=0.01
    )
    assert jump.spot_at(EXPIRY, at(D1, "10:15")) != pytest.approx(24012.0, abs=1)


def test_a_flat_market_with_no_stop_holds_to_the_next_session_exit_time():
    bars = make_bars([D1, D2], lambda ts: 24000.0)
    r = intraday.simulate(
        bars, context([D1, D2]), Rules(stop_pts=None, target_pts=None, reverse=False, **BASE)
    )
    assert len(r.trades) == 1
    t = r.trades[0]
    assert t["entry"] == at(D1, "10:15") and t["exit"] == at(D2, "15:00")
    assert (t["sold"], t["long"], t["side"], t["reason"]) == (24000.0, 23600.0, "PE", "time")
    assert t["credit"] == pytest.approx(100.0) and t["pts"] == pytest.approx(0.0, abs=0.01)


def test_the_target_closes_the_spread_when_it_has_decayed():
    bars = make_bars([D1, D2], lambda ts: 24000.0 if ts < at(D1, "13:00") else 24800.0)
    r = intraday.simulate(
        bars, context([D1, D2]), Rules(stop_pts=None, target_pts=10.0, reverse=False, **BASE)
    )
    t = r.trades[0]
    # The 12:55 bar closes at 13:00, when the market moves.
    assert t["reason"] == "target" and t["exit"] == at(D1, "12:55") and t["exit_value"] <= 10.0
    assert t["pts"] > 85


def _ramp_down(ts):
    """Flat, then a 150-point fall inside the 12:00 bar, then flat."""
    start, end = at(D1, "12:00"), at(D1, "12:05")
    if ts <= start:
        return 24000.0
    if ts >= end:
        return 23850.0
    return 24000.0 - 150.0 * (ts - start) / (end - start)


def test_a_stop_fills_at_the_trigger_plus_slippage_when_the_bar_crosses_it():
    bars = make_bars([D1, D2], _ramp_down)
    rules = Rules(stop_pts=43.8, stop_slip_pts=2.0, target_pts=None, reverse=False, **BASE)
    t = intraday.simulate(bars, context([D1, D2]), rules).trades[0]
    assert t["reason"] == "stop" and t["exit"] == at(D1, "12:00")
    assert t["exit_value"] == pytest.approx(100.0 + 43.8 + 2.0, abs=0.01)
    assert t["pts"] == pytest.approx(-45.8, abs=0.01)


def test_a_gap_through_the_stop_fills_at_the_opening_price():
    bars = make_bars(
        [D1, D2], lambda ts: 24000.0 if ts < at(D1, "12:00") else 23850.0, flat_bars=True
    )
    rules = Rules(stop_pts=43.8, stop_slip_pts=2.0, target_pts=None, reverse=False, **BASE)
    t = intraday.simulate(bars, context([D1, D2]), rules).trades[0]
    assert t["reason"] == "stop"
    assert (
        t["exit_value"] > 100.0 + 43.8 + 2.0 + 10
    )  # worse than the trigger, because the price jumped


def test_a_stop_reverses_to_the_other_side_on_the_next_bar_only_when_asked():
    bars = make_bars([D1, D2], _ramp_down)
    base = dict(stop_pts=43.8, target_pts=None, **BASE)
    with_reverse = intraday.simulate(bars, context([D1, D2]), Rules(reverse=True, **base)).trades
    without = intraday.simulate(bars, context([D1, D2]), Rules(reverse=False, **base)).trades
    assert len(without) == 1
    assert [t["side"] for t in with_reverse[:2]] == ["PE", "CE"]
    assert with_reverse[1]["entry"] == with_reverse[0]["exit"] + intraday.BAR


def test_a_position_held_overnight_blocks_the_next_entry():
    bars = make_bars([D1, D2, D3], lambda ts: 24000.0)
    r = intraday.simulate(
        bars, context([D1, D2, D3]), Rules(stop_pts=None, target_pts=None, reverse=False, **BASE)
    )
    # Entered D1 10:15, held to D2 15:00, so D2 10:15 is skipped; D3 is expiry day and enters again.
    assert [t["entry"].normalize() for t in r.trades] == [D1, D3]
    assert r.trades[1]["reason"] == "expiry"


def test_filters_skip_and_say_why():
    bars = make_bars([D1, D2], lambda ts: 24000.0)
    high_vix = intraday.simulate(
        bars, context([D1, D2], vix=25.0), Rules(vix_ceiling=20.0, gap_floor=None, side_rule="put")
    )
    assert not high_vix.trades and high_vix.skipped["vix ceiling"] == 2
    gap_down = intraday.simulate(
        bars,
        context([D1, D2], prev_close=24400.0),
        Rules(vix_ceiling=None, gap_floor=-0.01, side_rule="put"),
    )
    assert not gap_down.trades and gap_down.skipped["gap down"] == 2


@pytest.mark.parametrize(
    "spot,prev_close,rule,expected",
    [
        (24000.0, 23900.0, "vs_prev_close", "PE"),
        (24000.0, 24100.0, "vs_prev_close", "CE"),
        (24000.0, 23900.0, "fade", "CE"),
        (24000.0, 24100.0, "fade", "PE"),
    ],
)
def test_side_rules_use_the_prior_close(spot, prev_close, rule, expected):
    bars = make_bars([D1, D2], lambda ts: spot)
    r = intraday.simulate(
        bars,
        context([D1, D2], prev_close=prev_close),
        Rules(
            stop_pts=None,
            target_pts=None,
            reverse=False,
            vix_ceiling=None,
            gap_floor=None,
            side_rule=rule,
        ),
    )
    assert r.trades[0]["side"] == expected


def test_the_lot_size_follows_the_exchange_change():
    assert intraday.lot_size_for(pd.Timestamp("2025-07-09")) == 75
    assert intraday.lot_size_for(pd.Timestamp("2026-01-02")) == 65


def test_replaying_a_published_entry_prices_it_from_the_bars():
    bars = make_bars([D1, D2], lambda ts: 24000.0)
    rows = [
        {"ent": at(D1, "10:17"), "kind": "PE", "sold": 24000.0, "long": 23600.0, "credit": 99.0}
    ]
    out = intraday.replay_published(
        bars, rows, Rules(stop_pts=None, target_pts=None, reverse=False)
    )
    assert len(out) == 1 and out[0]["entry"] == at(D1, "10:15")
    assert out[0]["credit"] == pytest.approx(100.0) and out[0]["published_credit"] == 99.0


def test_bars_load_from_the_files_the_fetcher_writes(tmp_path):
    bars = make_bars([D1], lambda ts: 24000.0, strikes=[24000, 23600])
    for (expiry, kind, strike), frame in bars._frames.items():
        frame.rename_axis("timestamp").to_csv(
            tmp_path / f"{expiry:%Y-%m-%d}_{kind}_{int(strike)}.csv"
        )
    loaded = OptionBars.load(tmp_path)
    assert loaded.expiries() == [EXPIRY] and loaded.days() == [D1]
    assert loaded.pair(EXPIRY, "PE", 24000, 23600) is not None


# --- the fetcher ------------------------------------------------------------


def test_candles_come_back_ascending_in_exchange_clock_time():
    payload = {
        "data": {
            "candles": [
                ["2026-03-02T09:20:00+05:30", 11, 12, 10, 11.5, 100, 5],
                ["2026-03-02T09:15:00+05:30", 10, 11, 9, 10.5, 90, 4],
            ]
        }
    }
    frame = fetch.parse_candles(payload)
    assert list(frame.index) == [pd.Timestamp("2026-03-02 09:15"), pd.Timestamp("2026-03-02 09:20")]
    assert frame["open"].tolist() == [10, 11]


def test_contract_listing_maps_kind_and_strike_to_the_instrument_key():
    payload = {
        "data": [
            {
                "instrument_type": "PE",
                "strike_price": 24000.0,
                "instrument_key": "NSE_FO|1|02-03-2026",
            },
            {
                "instrument_type": "CE",
                "strike_price": 24050.0,
                "instrument_key": "NSE_FO|2|02-03-2026",
            },
        ]
    }
    assert fetch.parse_contracts(payload) == {
        ("PE", 24000.0): "NSE_FO|1|02-03-2026",
        ("CE", 24050.0): "NSE_FO|2|02-03-2026",
    }


def _server(seen, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("authorization")))
        if status != 200:
            return httpx.Response(
                status, json={"errors": [{"errorCode": "UDAPI1149"}]} if status == 403 else {}
            )
        if request.url.path.endswith("/option/contract"):
            data = [
                {
                    "instrument_type": k,
                    "strike_price": float(s),
                    "instrument_key": f"NSE_FO|{k}{s}|x",
                }
                for k in ("CE", "PE")
                for s in (23500, 23550)
            ]
            return httpx.Response(200, json={"status": "success", "data": data})
        return httpx.Response(
            200, json={"data": {"candles": [["2026-03-02T09:15:00+05:30", 1, 2, 1, 2, 3, 4]]}}
        )

    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.upstox.com",
        headers={"Authorization": "Bearer SECRET"},
    )


def test_the_download_writes_one_file_per_contract_and_resumes_without_asking_again(tmp_path):
    seen: list = []
    items = [(EXPIRY, D1, 23500.0, 23550.0)]
    first = fetch.run(_server(seen), items, tmp_path, sleep=0, dry_run=False, log=lambda *_: None)
    assert first["files"] == 4 and len(list(tmp_path.glob("*.csv"))) == 4
    assert "SECRET" not in "".join(p.read_text() for p in tmp_path.glob("*.csv"))
    # The expired-instrument key is URL-encoded in the path.
    assert any("NSE_FO%7CPE23500%7Cx" in url for url, _ in seen)
    again: list = []
    second = fetch.run(_server(again), items, tmp_path, sleep=0, dry_run=False, log=lambda *_: None)
    assert again == [] and second["already_on_disk"] == 4 and second["files"] == 0


def test_a_dry_run_counts_requests_and_makes_none(tmp_path):
    seen: list = []
    result = fetch.run(
        _server(seen), [(EXPIRY, D1, 23500.0, 23550.0)], tmp_path, sleep=0, dry_run=True
    )
    assert seen == [] and result["calls"] == 1 + 4 and not list(tmp_path.iterdir())


def test_a_missing_plan_or_bad_token_is_explained_in_plain_words(tmp_path):
    for status, words in ((403, "Plus plan"), (401, "token")):
        with pytest.raises(fetch.FetchError) as caught:
            fetch.run(
                _server([], status),
                [(EXPIRY, D1, 23500.0, 23550.0)],
                tmp_path,
                sleep=0,
                dry_run=False,
            )
        assert (
            words in str(caught.value)
            and "403" not in str(caught.value)
            and "401" not in str(caught.value)
        )


def test_the_plan_covers_the_strikes_a_week_of_spreads_could_touch(tmp_path):
    days = tmp_path / "days"
    days.mkdir()
    for day in (D1, D2):
        pd.DataFrame(
            {
                "date": [day],
                "expiry": [EXPIRY],
                "strike": [24000.0],
                "kind": ["PE"],
                "open": [1.0],
                "close": [1.0],
                "volume": [1],
                "oi": [1],
            }
        ).to_csv(days / f"{day:%Y%m%d}.csv", index=False)
    pd.DataFrame(
        {"Date": [D1, D2], "Open": [24020.0, 23980.0], "Close": [24000.0, 24000.0]}
    ).to_csv(tmp_path / "nsei.csv", index=False)
    ((expiry, first, low, high),) = fetch.plan(tmp_path, days, None, None)
    assert (expiry, first) == (EXPIRY, D1)
    assert (
        low == 23450.0 and high == 24550.0
    )  # opens 23980..24020, less/plus the 400 width and a 100 margin


def test_the_strike_is_chosen_from_what_was_known_before_the_entry_bar():
    # The market starts moving inside the 10:15 bar. The strike must still come from 24000.
    bars = make_bars([D1, D2], lambda ts: 24000.0 if ts <= at(D1, "10:15") else 24300.0)
    rules = Rules(stop_pts=None, target_pts=None, reverse=False, **BASE)
    assert intraday.simulate(bars, context([D1, D2]), rules).trades[0]["sold"] == 24000.0
