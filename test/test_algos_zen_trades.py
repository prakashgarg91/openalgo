"""Tests for services/algos/zen_trades.py using synthetic records shaped like the export."""

import copy
import json
from datetime import date
from pathlib import Path

import pytest

from services.algos.zen_trades import (
    IST,
    ZenTrade,
    load_trades,
    parse_symbol,
    parse_trade,
    rejection_reason,
    summarize,
)

REAL_FILE = Path(
    "D:/Github/trading-rex-ai/agent-results/022-stratzy/raw/pastAdvices/68596cd26aa2cba24bbb67da.json"
)


def _leg(symbol, side, entry, exit_price, multiplier=65):
    return {
        "_id": "leg-" + symbol,
        "quantity": 1,
        "isActive": False,
        "entryPrice": entry,
        "symbol": symbol,
        "transactionType": side,
        "multiplier": multiplier,
        "exitPrice": exit_price,
        "finalExitPrice": exit_price,
        "avgExitPrice": exit_price,
    }


def _record(
    *,
    advice_id="adv-1",
    created="2026-09-23T04:47:31.406Z",
    closed="2026-09-24T03:46:35.593Z",
    legs=None,
    lots=5,
    pnl=13000,
    title="Final Exit",
    state="EXECUTED",
):
    return {
        "_id": advice_id,
        "name": "Zen Credit Spread Overnight:23/09/2026 10:17",
        "createdAt": created,
        "closedOn": closed,
        "executionState": state,
        "type": "F&O",
        "subCategory": "Credit Spread",
        "trades": legs if legs is not None else [],
        "summary": [
            {"title": title, "pnl": pnl, "lotsTraded": lots, "trades": [], "closedOn": closed}
        ],
        "maxLots": lots,
        "pnl": pnl,
        "marginRequired": 50000.0,
    }


def _put_record(**kwargs):
    # Sold 23400PE at 100 entry, 50 exit. Long 23000PE at 20 entry, 10 exit.
    legs = [
        _leg("NIFTY26SEP23000PE", "BUY", 20.0, 10.0),
        _leg("NIFTY26SEP23400PE", "SELL", 100.0, 50.0),
    ]
    kwargs.setdefault("legs", legs)
    kwargs.setdefault("pnl", 13000)  # (80 - 40) * 5 * 65
    return _record(**kwargs)


def _call_record(**kwargs):
    # Weekly call credit spread: sold 23450CE at 90 -> 10, long 23850CE at 30 -> 4.
    legs = [
        _leg("NIFTY2692223850CE", "BUY", 30.0, 4.0, multiplier=75),
        _leg("NIFTY2692223450CE", "SELL", 90.0, 10.0, multiplier=75),
    ]
    kwargs.setdefault("legs", legs)
    kwargs.setdefault("lots", 4)
    kwargs.setdefault("pnl", 16200)  # (60 - 6) * 4 * 75
    kwargs.setdefault("title", "Stop Loss")
    kwargs.setdefault("created", "2026-09-22T05:00:00.000Z")  # 10:30 IST
    return _record(**kwargs)


def test_put_spread_parses_fields():
    trade = parse_trade(_put_record())
    assert trade is not None
    assert trade.advice_id == "adv-1"
    assert trade.kind == "PE"
    assert trade.sold_symbol == "NIFTY26SEP23400PE"
    assert trade.long_symbol == "NIFTY26SEP23000PE"
    assert trade.sold_strike == 23400.0
    assert trade.long_strike == 23000.0
    assert trade.width == 400.0
    assert trade.expiry is None  # monthly symbol carries no day
    assert trade.lots == 5
    assert trade.lot_size == 65
    assert trade.entry_credit == pytest.approx(80.0)
    assert trade.exit_debit == pytest.approx(40.0)
    assert trade.pnl == 13000
    assert trade.margin == 50000.0
    assert trade.exit_class == "unknown"
    assert trade.entry_time.utcoffset() == IST.utcoffset(None)
    assert trade.entry_time.hour == 10 and trade.entry_time.minute == 17
    assert trade.exit_time is not None and trade.exit_time.utcoffset() == IST.utcoffset(None)


def test_call_spread_parses_fields_and_stop_label():
    trade = parse_trade(_call_record())
    assert trade is not None
    assert trade.kind == "CE"
    assert trade.sold_strike == 23450.0
    assert trade.long_strike == 23850.0
    assert trade.width == 400.0
    assert trade.expiry == date(2026, 9, 22)  # weekly symbol: yy, month 9, dd 22
    assert trade.lots == 4
    assert trade.lot_size == 75
    assert trade.entry_credit == pytest.approx(60.0)
    assert trade.exit_debit == pytest.approx(6.0)
    assert trade.pnl == 16200
    assert trade.exit_class == "stop"
    assert trade.entry_time.hour == 10 and trade.entry_time.minute == 30


def test_missing_exit_price_gives_none_debit_not_rejection():
    legs = [
        _leg("NIFTY26SEP23000PE", "BUY", 20.0, None),
        _leg("NIFTY26SEP23400PE", "SELL", 100.0, None),
    ]
    for leg in legs:
        leg.pop("avgExitPrice")
        leg.pop("exitPrice")
        leg.pop("finalExitPrice")
    trade = parse_trade(_put_record(legs=legs))
    assert trade is not None
    assert trade.exit_debit is None
    assert trade.entry_credit == pytest.approx(80.0)


@pytest.mark.parametrize(
    "record",
    [
        pytest.param(_put_record(state="PENDING"), id="not-executed"),
        pytest.param(_put_record(state="CANCELLED"), id="cancelled"),
        pytest.param(
            _record(legs=[_leg("NIFTY26SEP23400PE", "SELL", 100.0, 50.0)]),
            id="one-leg",
        ),
        pytest.param(
            _record(
                legs=[
                    _leg("NIFTY26SEP23000PE", "SELL", 20.0, 10.0),
                    _leg("NIFTY26SEP23400PE", "SELL", 100.0, 50.0),
                ]
            ),
            id="two-sells",
        ),
        pytest.param(
            _record(
                legs=[
                    _leg("NIFTY26SEP23000PE", "BUY", None, 10.0),
                    _leg("NIFTY26SEP23400PE", "SELL", 100.0, 50.0),
                ]
            ),
            id="missing-entry-price",
        ),
        pytest.param(
            _record(
                legs=[
                    _leg("NIFTY26SEP23000PE", "BUY", 20.0, 10.0),
                    _leg("NIFTY26SEP23400CE", "SELL", 100.0, 50.0),
                ]
            ),
            id="mixed-kind",
        ),
        pytest.param(
            _record(
                legs=[
                    _leg("NIFTY26SEP23000PE", "BUY", 20.0, 10.0),
                    _leg("BANKNIFTY-FUT", "SELL", 100.0, 50.0),
                ]
            ),
            id="unparseable-symbol",
        ),
        pytest.param(
            _record(
                legs=[
                    _leg("NIFTY26SEP23000PE", "BUY", 20.0, 10.0),
                    _leg("NIFTY26SEP23400PE", "SELL", 100.0, 50.0),
                ],
                pnl=None,
            ),
            id="no-pnl",
        ),
        pytest.param("not a dict", id="not-a-dict"),
        pytest.param({"executionState": "EXECUTED"}, id="empty-object"),
    ],
)
def test_unexecuted_or_malformed_records_return_none(record):
    assert parse_trade(record) is None
    assert rejection_reason(record) is not None


def test_bad_entry_time_rejected():
    assert parse_trade(_put_record(created="not-a-date")) is None
    assert parse_trade(_put_record(created="2026-09-23T04:47:31")) is None  # no zone


def test_load_trades_sorts_by_entry_time_and_skips_bad(tmp_path):
    later = _put_record(advice_id="later", created="2026-09-23T04:47:31.000Z")
    earlier = _call_record(advice_id="earlier", created="2026-09-21T04:30:00.000Z")
    bad = _record(advice_id="bad", legs=[_leg("NIFTY26SEP23400PE", "SELL", 100.0, 50.0)])
    path = tmp_path / "advices.json"
    path.write_text(
        json.dumps({"success": True, "message": "ok", "pastAdvices": [later, bad, earlier]}),
        encoding="utf-8",
    )
    trades = load_trades(path)
    assert [t.advice_id for t in trades] == ["earlier", "later"]
    assert all(isinstance(t, ZenTrade) for t in trades)


def test_load_trades_rejects_wrong_shape(tmp_path):
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"success": True}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_trades(path)


def _trade(pnl, kind="PE"):
    base = parse_trade(_put_record())
    return ZenTrade(**{**base.__dict__, "pnl": pnl, "kind": kind})


def test_summarize_hand_computed():
    # pnls: +1000, -500, +2000, -1000, 0 (zero counts as neither win nor loss)
    trades = [
        _trade(1000, "CE"),
        _trade(-500, "PE"),
        _trade(2000, "PE"),
        _trade(-1000, "CE"),
        _trade(0, "PE"),
    ]
    s = summarize(trades)
    assert s["count"] == 5
    assert s["wins"] == 2
    assert s["win_rate"] == pytest.approx(0.4)
    assert s["net"] == pytest.approx(1500)
    assert s["average_win"] == pytest.approx(1500)  # (1000 + 2000) / 2
    assert s["average_loss"] == pytest.approx(-750)  # (-500 - 1000) / 2
    assert s["profit_factor"] == pytest.approx(2.0)  # 3000 / 1500
    assert s["worst"] == -1000
    assert s["calls"] == {"count": 2, "net": pytest.approx(0)}
    assert s["puts"] == {"count": 3, "net": pytest.approx(1500)}


def test_summarize_empty_and_no_losses():
    empty = summarize([])
    assert empty["count"] == 0
    assert empty["win_rate"] is None
    assert empty["profit_factor"] is None
    assert empty["worst"] is None
    assert empty["net"] == 0

    wins_only = summarize([_trade(100), _trade(200)])
    assert wins_only["profit_factor"] is None  # no gross loss to divide by
    assert wins_only["average_loss"] is None


@pytest.mark.parametrize(
    "symbol, expected",
    [
        ("NIFTY26SEP23000PE", ("PE", 23000.0, None)),
        ("NIFTY26SEP23400CE", ("CE", 23400.0, None)),
        ("NIFTY2692223450PE", ("PE", 23450.0, date(2026, 9, 22))),
        ("NIFTY26D0323000CE", ("CE", 23000.0, date(2026, 12, 3))),
        ("NIFTY26O0523000PE", ("PE", 23000.0, date(2026, 10, 5))),
        ("NIFTY26N1223000PE", ("PE", 23000.0, date(2026, 11, 12))),
    ],
)
def test_symbol_formats(symbol, expected):
    parsed = parse_symbol(symbol)
    assert parsed is not None
    assert (parsed.kind, parsed.strike, parsed.expiry) == expected


@pytest.mark.parametrize(
    "symbol", ["NIFTY26XYZ23000PE", "NIFTY23000", "", None, 123, "NIFTY2613223000PE"]
)
def test_unparseable_symbols(symbol):
    assert parse_symbol(symbol) is None


def test_record_not_mutated_by_parsing():
    record = _put_record()
    snapshot = copy.deepcopy(record)
    parse_trade(record)
    assert record == snapshot


@pytest.mark.skipif(not REAL_FILE.exists(), reason="real Zen export is outside this repo")
def test_real_export_parses():
    trades = load_trades(REAL_FILE)
    assert len(trades) >= 200
    assert all(t.width == 400 for t in trades)
    assert all(9 <= t.entry_time.hour <= 15 for t in trades)
    assert all(t.entry_credit is not None for t in trades)


@pytest.mark.skipif(not REAL_FILE.exists(), reason="the Zen file is outside this repository")
def test_the_real_file_keeps_each_legs_entry_and_exit_price_when_the_record_has_them():
    first = load_trades(REAL_FILE)[0]
    assert first.sold_entry is not None and first.long_entry is not None
    assert abs((first.sold_entry - first.long_entry) - first.entry_credit) < 1e-9
    if first.exit_debit is not None:
        assert abs((first.sold_exit - first.long_exit) - first.exit_debit) < 1e-9


def test_a_jsonl_file_with_one_advice_per_line_loads_the_same_way(tmp_path):
    advices = (
        json.loads(REAL_FILE.read_text(encoding="utf-8"))["pastAdvices"][:5]
        if REAL_FILE.exists()
        else []
    )
    if not advices:
        pytest.skip("the Zen file is outside this repository")
    lines = [json.dumps(a) for a in advices]
    path = tmp_path / "zen.jsonl"
    path.write_text("\n".join([*lines, "", "not json"]) + "\n", encoding="utf-8")
    from_lines = load_trades(path)
    plain = tmp_path / "zen.json"
    plain.write_text(json.dumps({"pastAdvices": advices}), encoding="utf-8")
    assert [t.advice_id for t in from_lines] == [t.advice_id for t in load_trades(plain)]
