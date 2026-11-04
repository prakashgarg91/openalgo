import json
import math
from datetime import datetime

import pytest

from services.algos.pick_log import PickLog, rank_correlation, summarize

NOW = datetime(2026, 11, 4, 10, 0, 0)


def make_pick(**overrides):
    pick = {
        "template_id": "iron-condor",
        "name": "Iron condor",
        "fit": 62.5,
        "components": {"trend": 40},
        "expiry": "2026-11-26",
        "legs": [{"kind": "CE", "strike": 22000, "side": "B", "qty": 1, "price": 100.0}],
        "lot": 75,
        "capital_required": 15000,
        "max_loss": 5000,
        "conditions": {"vix_below": 20},
    }
    pick.update(overrides)
    return pick


def closed_pick(index, fit, pnl):
    return {
        "id": f"p{index}",
        "status": "closed",
        "fit": fit,
        "pnl": pnl,
    }


def test_add_and_all_roundtrip_with_incrementing_ids(tmp_path):
    path = tmp_path / "deep" / "folder" / "picks.jsonl"
    log = PickLog(path)
    assert log.all() == []

    first = log.add(make_pick(), NOW)
    second = log.add(make_pick(name="Second"), NOW)

    assert first["id"] == "20261104100000-1"
    assert second["id"] == "20261104100000-2"
    assert first["status"] == "open"
    assert first["pnl"] is None
    assert first["closed"] is None
    assert first["opened"] == NOW.isoformat()

    picks = log.all()
    assert [p["id"] for p in picks] == [first["id"], second["id"]]
    assert picks[1]["name"] == "Second"


def test_missing_key_is_named(tmp_path):
    pick = make_pick()
    del pick["fit"]
    with pytest.raises(ValueError) as exc:
        PickLog(tmp_path / "picks.jsonl").add(pick, NOW)
    assert str(exc.value) == "The pick is missing fit."


def test_empty_legs_are_rejected(tmp_path):
    with pytest.raises(ValueError) as exc:
        PickLog(tmp_path / "picks.jsonl").add(make_pick(legs=[]), NOW)
    assert str(exc.value) == "Every leg needs a type, strike, side, quantity and entry price."


def test_bad_side_is_rejected(tmp_path):
    legs = [{"kind": "CE", "strike": 22000, "side": "X", "qty": 1, "price": 100.0}]
    with pytest.raises(ValueError) as exc:
        PickLog(tmp_path / "picks.jsonl").add(make_pick(legs=legs), NOW)
    assert str(exc.value) == "Every leg needs a type, strike, side, quantity and entry price."


def test_fit_above_100_is_rejected(tmp_path):
    with pytest.raises(ValueError) as exc:
        PickLog(tmp_path / "picks.jsonl").add(make_pick(fit=150), NOW)
    assert str(exc.value) == "The fit score must be a number between 0 and 100."


def test_close_sets_result_and_refuses_repeat_or_unknown(tmp_path):
    log = PickLog(tmp_path / "picks.jsonl")
    pick = log.add(make_pick(), NOW)

    closed = log.close(pick["id"], 150.5, NOW)

    assert closed["status"] == "closed"
    assert closed["pnl"] == 150.5
    assert closed["closed"] == NOW.isoformat()
    assert log.all()[0]["status"] == "closed"

    with pytest.raises(ValueError) as repeat:
        log.close(pick["id"], 10, NOW)
    assert str(repeat.value) == "This pick is already closed."

    with pytest.raises(ValueError) as unknown:
        log.close("no-such-id", 10, NOW)
    assert str(unknown.value) == "No such pick."


def test_file_survives_a_reopened_log(tmp_path):
    path = tmp_path / "picks.jsonl"
    first = PickLog(path)
    pick = first.add(make_pick(), NOW)
    first.close(pick["id"], -40, NOW)

    reopened = PickLog(path)
    picks = reopened.all()
    assert len(picks) == 1
    assert picks[0]["status"] == "closed"
    assert picks[0]["pnl"] == -40.0

    again = reopened.add(make_pick(), NOW)
    assert again["id"] == "20261104100000-2"


def test_corrupt_line_is_skipped(tmp_path):
    path = tmp_path / "picks.jsonl"
    log = PickLog(path)
    log.add(make_pick(), NOW)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    log.add(make_pick(name="After"), NOW)

    picks = log.all()
    assert [p["name"] for p in picks] == ["Iron condor", "After"]


def test_closing_keeps_a_corrupt_line_in_place(tmp_path):
    path = tmp_path / "picks.jsonl"
    log = PickLog(path)
    pick = log.add(make_pick(), NOW)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    log.close(pick["id"], 20, NOW)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[1] == "{not json"
    assert json.loads(lines[0])["status"] == "closed"


def test_mark_long_call_and_short_put(tmp_path):
    pick = {
        "lot": 75,
        "legs": [
            {"kind": "CE", "strike": 22000, "side": "B", "qty": 1, "price": 100.0},
            {"kind": "PE", "strike": 21000, "side": "S", "qty": 2, "price": 80.0},
        ],
    }
    mids = {("CE", 22000.0): 130.0, ("PE", 21000.0): 70.0}

    # long call: +1 * 1 * (130 - 100) = 30; short put: -1 * 2 * (70 - 80) = 20
    assert PickLog.mark(pick, mids) == 75 * 50

    assert PickLog.mark(pick, {("CE", 22000.0): 130.0}) is None


def test_rank_correlation_values():
    assert rank_correlation([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert rank_correlation([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    assert rank_correlation([1, 2, 3, 4], [5, 5, 5, 5]) is None
    assert rank_correlation([1, 2], [1, 2]) is None

    # ties: x ranks [1.5, 1.5, 3, 4], y ranks [1, 2, 3, 4]
    expected = 4.5 / math.sqrt(4.5 * 5.0)
    assert rank_correlation([1, 1, 2, 3], [1, 2, 3, 4]) == pytest.approx(expected)


def test_summarize_three_closed_picks_is_too_few():
    picks = [closed_pick(i, 50 + i, 10 * i) for i in range(3)]

    result = summarize(picks)

    assert result["closed"] == 3
    assert result["correlation"] is None
    assert (
        result["verdict"]
        == "Too few closed picks (3 of 20) to say whether the fit score means anything."
    )


def test_summarize_twelve_rising_picks_still_too_few():
    picks = [closed_pick(i, 50 + 4 * i, 10 * i) for i in range(12)]

    result = summarize(picks)

    assert result["correlation"] > 0.3
    assert (
        result["verdict"]
        == "Too few closed picks (12 of 20) to say whether the fit score means anything."
    )


def test_summarize_twenty_rising_picks_gives_a_verdict():
    picks = [closed_pick(i, 50 + 2 * i, 10 * i - 50) for i in range(20)]

    result = summarize(picks)

    assert result["closed"] == 20
    assert result["correlation"] == pytest.approx(1.0)
    assert result["verdict"] == "Higher fit scores tended to do better."


def test_open_picks_are_counted_but_not_measured():
    picks = [closed_pick(i, 50 + 2 * i, 10 * i - 50) for i in range(20)]
    picks += [{"id": "open-1", "status": "open", "fit": 99, "pnl": None}]
    picks += [{"id": "open-2", "status": "open", "fit": 10, "pnl": None}]

    result = summarize(picks)

    assert result["open"] == 2
    assert result["closed"] == 20
    assert result["wins"] == sum(1 for i in range(20) if 10 * i - 50 > 0)
    assert result["win_rate"] == round(result["wins"] / 20, 3)
    assert result["worst"] == -50.0
    assert result["best"] == 140.0
    assert result["total"] == round(sum(10 * i - 50 for i in range(20)), 2)
