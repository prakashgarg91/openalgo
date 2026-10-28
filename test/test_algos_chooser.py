from services.algos import chooser


def trades(label, pnls, start=1):
    return [
        {
            "date": f"2020-{1 + (start + i) // 28:02d}-{1 + (start + i) % 28:02d}",
            "regime": label,
            "pnl": p,
        }
        for i, p in enumerate(pnls)
    ]


NAMES = {"good": "Good", "bad": "Bad", "fading": "Fading"}


def table():
    # Dates are spread so 75 percent of the trades fall in the evidence period.
    good = [
        {
            "date": f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}",
            "regime": "calm",
            "pnl": 300.0 if i % 3 else -200.0,
        }
        for i in range(120)
    ]
    bad = [{"date": t["date"], "regime": "calm", "pnl": -150.0} for t in good]
    fading = [
        {"date": t["date"], "regime": "calm", "pnl": 250.0 if i < 90 else -400.0}
        for i, t in enumerate(good)
    ]
    return chooser.build_table({"good": good, "bad": bad, "fading": fading})


def test_picks_the_algo_that_held_up_and_explains_the_others():
    result = chooser.choose("calm", 1.0, table(), NAMES)
    assert result["pick"] == "good"
    by_id = {r["algo_id"]: r for r in result["candidates"]}
    assert by_id["bad"]["reasons"] and "lost money" in by_id["bad"]["reasons"][0]
    assert "newer years" in by_id["fading"]["reasons"][0]
    assert "Past results, not a promise" in result["headline"]


def test_stands_aside_when_nothing_has_earned_a_place():
    only_bad = chooser.build_table(
        {
            "bad": [
                {"date": f"2020-01-{i + 1:02d}", "regime": "calm", "pnl": -100.0} for i in range(28)
            ]
            * 3
        }
    )
    result = chooser.choose("calm", 1.0, only_bad, NAMES)
    assert result["pick"] is None and result["headline"].startswith("Standing aside")


def test_a_kind_of_day_with_no_history_stands_aside():
    result = chooser.choose("event", 1.0, table(), NAMES)
    assert result["pick"] is None
    assert all("only 0 past trades" in r["reasons"][0] for r in result["candidates"])


def test_unreliable_market_data_or_missing_table_stands_aside():
    assert chooser.choose("calm", 0.2, table(), NAMES)["pick"] is None
    assert chooser.choose("calm", 1.0, None, NAMES)["pick"] is None
    assert chooser.choose("calm", 1.0, {"algos": {}}, NAMES)["pick"] is None


def test_candidates_limit_who_may_be_picked():
    result = chooser.choose("calm", 1.0, table(), NAMES, candidates=["bad", "fading"])
    assert result["pick"] is None


def test_empty_history_builds_an_empty_table():
    assert chooser.build_table({"x": []})["algos"] == {}
