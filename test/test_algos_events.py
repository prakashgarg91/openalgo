"""Event days: what they block, what they refuse, and that the regime really changes."""

from datetime import date

import pytest

from services.algos import events
from services.algos.context import RegimeResult

TODAY = date(2026, 1, 20)  # a Tuesday


def regime(label="calm", confidence=0.9):
    return RegimeResult(label, "bullish", 0.1, confidence, ("quiet",), ("vix",))


@pytest.fixture
def path(tmp_path):
    return tmp_path / "events.json"


def test_add_list_remove_round_trip(path):
    events.add("2026-02-01", "Union Budget", TODAY, path)
    events.add("2026-01-30", "Results", TODAY, path)
    assert [e["date"] for e in events.load(path)] == ["2026-01-30", "2026-02-01"]
    events.add("2026-02-01", "Budget day", TODAY, path)  # same day replaces, no duplicate
    assert [e["label"] for e in events.load(path)] == ["Results", "Budget day"]
    events.remove("2026-01-30", path)
    assert [e["date"] for e in events.load(path)] == ["2026-02-01"]


@pytest.mark.parametrize(
    ("day", "label", "word"),
    [
        ("tomorrow", "x", "like 2026-02-01"),
        ("2026-01-01", "x", "from today"),
        ("2030-01-01", "x", "from today"),
        ("2026-02-01", "", "short name"),
        ("2026-02-01", "x" * 61, "short name"),
    ],
)
def test_bad_entries_are_refused_in_plain_words(path, day, label, word):
    with pytest.raises(events.EventError) as exc:
        events.add(day, label, TODAY, path)
    assert word in str(exc.value)


def test_the_list_is_capped(path):
    entries = [
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "label": "x"} for i in range(100)
    ]
    path.write_text(__import__("json").dumps(entries))
    with pytest.raises(events.EventError):
        events.add("2026-12-30", "one more", TODAY, path)


def test_an_event_blocks_its_day_and_the_trading_day_before():
    entries = [{"date": "2026-02-04", "label": "Policy decision"}]  # a Wednesday
    assert events.blocking(date(2026, 2, 3), entries) == "Policy decision"
    assert events.blocking(date(2026, 2, 4), entries) == "Policy decision"
    assert events.blocking(date(2026, 2, 2), entries) is None
    assert events.blocking(date(2026, 2, 5), entries) is None


def test_a_monday_event_also_blocks_the_friday_before():
    entries = [{"date": "2026-02-02", "label": "Budget"}]  # a Monday
    for blocked in (date(2026, 1, 30), date(2026, 1, 31), date(2026, 2, 1), date(2026, 2, 2)):
        assert events.blocking(blocked, entries) == "Budget"
    assert events.blocking(date(2026, 1, 29), entries) is None


def test_apply_relabels_the_regime_as_event_and_says_why():
    entries = [{"date": "2026-01-21", "label": "Union Budget"}]
    out = events.apply(regime(), TODAY, entries)
    assert out.label == "event" and out.reasons[0] == "You marked Union Budget as a day to sit out."
    assert out.confidence == 1.0 and out.bias == "bullish"
    untouched = events.apply(regime(), date(2026, 3, 3), entries)
    assert untouched.label == "calm"


def test_an_event_day_makes_every_algo_stand_aside():
    from services.algos.templates import ALGOS, build

    ev = events.apply(regime(), TODAY, [{"date": "2026-01-20", "label": "Results"}])
    for algo_id in ALGOS:
        if algo_id == "smart_pick":
            continue
        plan = build(algo_id, ev, capital=500_000, lot_size=75, days_to_expiry=4)
        assert plan.action == "skip", algo_id


def test_a_damaged_file_means_no_events_not_a_crash(path):
    path.write_text("{not json")
    assert events.load(path) == []
    path.write_text('[{"date": "2026-02-01"}, 5, {"date": "2026-02-02", "label": "ok"}]')
    assert [e["label"] for e in events.load(path)] == ["ok"]
