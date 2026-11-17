"""Cell labels for trading days, on made-up facts.

Pure functions only: nothing here reads a database, a broker, the network, the clock or a file.
"""

import itertools

from services.algos import portfolio_labels as pl


def day(**overrides) -> dict:
    base = {
        "vix_prev": 12.0,
        "range_prev_pct": 0.5,
        "gap_pct": 0.1,
        "is_expiry": False,
        "is_event": False,
    }
    base.update(overrides)
    return base


def test_vix_boundaries_pick_the_band():
    assert pl.volatility_band(13.99, 0.5) == "low"
    assert pl.volatility_band(14.0, 0.5) == "mid"
    assert pl.volatility_band(17.99, 0.5) == "mid"
    assert pl.volatility_band(18.0, 0.5) == "high"


def test_wide_previous_range_moves_one_band_up():
    assert pl.volatility_band(13.0, 1.0) == "mid"  # low -> mid at the split
    assert pl.volatility_band(13.0, 0.99) == "low"
    assert pl.volatility_band(15.0, 2.5) == "high"  # mid -> high
    assert pl.volatility_band(20.0, 5.0) == "high"  # high stays high


def test_missing_range_does_not_bump():
    assert pl.volatility_band(13.0, None) == "low"


def test_missing_vix_is_unlabelled_band():
    assert pl.volatility_band(None, 2.0) is None
    assert pl.volatility_band(None, None) is None


def test_gap_helper_boundaries_use_absolute_value():
    # gap_size is kept as a helper; label_day does not use it.
    assert pl.gap_size(0.49) == "small"
    assert pl.gap_size(0.5) == "large"
    assert pl.gap_size(-0.5) == "large"
    assert pl.gap_size(-0.49) == "small"
    assert pl.gap_size(None) is None


def test_label_ignores_gap_and_expiry():
    assert pl.label_day(day(gap_pct=3.0, is_expiry=True)) == "low"
    assert pl.label_day(day(gap_pct=None, is_expiry=True)) == "low"
    assert pl.label_day(day(gap_pct=-0.6)) == "low"


def test_event_overrides_everything():
    assert pl.label_day(day(is_event=True)) == "event"
    assert pl.label_day(day(is_event=True, vix_prev=None, gap_pct=None)) == "event"
    assert pl.label_day(day(is_event=True, is_expiry=True, gap_pct=3.0)) == "event"


def test_missing_vix_gives_unlabelled():
    assert pl.label_day(day(vix_prev=None)) == "unlabelled"
    assert pl.label_day(day(vix_prev=None, range_prev_pct=None)) == "unlabelled"


def test_label_is_the_band():
    assert pl.label_day(day()) == "low"
    assert pl.label_day(day(vix_prev=15.0)) == "mid"
    assert pl.label_day(day(vix_prev=15.0, range_prev_pct=1.2)) == "high"


def test_all_cells_has_five_sorted_entries():
    cells = pl.all_cells()
    assert cells == ["event", "high", "low", "mid", "unlabelled"]
    assert cells == sorted(cells)
    assert len(set(cells)) == 5


def test_every_label_is_in_all_cells():
    cells = set(pl.all_cells())
    vix_values = [None, 0.0, 13.99, 14.0, 15.0, 17.99, 18.0, 30.0]
    range_values = [None, 0.0, 0.99, 1.0, 3.0]
    gap_values = [None, -0.6, -0.5, -0.49, 0.0, 0.49, 0.5, 2.0]
    for vix, rng, gap, expiry, event in itertools.product(
        vix_values, range_values, gap_values, (False, True), (False, True)
    ):
        label = pl.label_day(
            {
                "vix_prev": vix,
                "range_prev_pct": rng,
                "gap_pct": gap,
                "is_expiry": expiry,
                "is_event": event,
            }
        )
        assert label in cells, label


def test_no_look_ahead_label_depends_only_on_its_own_day():
    today = day(vix_prev=15.0, range_prev_pct=0.4, gap_pct=0.7, is_expiry=True)
    first = pl.label_day(today)

    # Unrelated days, including one with extreme values, are labelled in between.
    pl.label_day(day(vix_prev=40.0, range_prev_pct=9.0, gap_pct=-4.0, is_event=True))
    pl.label_day(day(vix_prev=None, gap_pct=None))

    # The same day, given again after the others, must get the same label.
    second = pl.label_day(today)
    assert first == second == "mid"

    # Changing the next day's dict must not move today's label.
    tomorrow = day(vix_prev=25.0, gap_pct=0.0)
    pl.label_day(tomorrow)
    assert pl.label_day(today) == "mid"


def test_nan_inputs_count_as_missing_not_as_numbers():
    nan = float("nan")
    base = {
        "vix_prev": 15.0,
        "range_prev_pct": 0.5,
        "gap_pct": 0.1,
        "is_expiry": False,
        "is_event": False,
    }
    assert pl.label_day({**base, "vix_prev": nan}) == "unlabelled"
    assert pl.label_day({**base, "range_prev_pct": nan}) == "mid"
    assert pl.label_day({**base, "gap_pct": nan}) == "mid"
