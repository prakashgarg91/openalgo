"""Tests for the vendor decider and its guarded run script. Synthetic data only, no network."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import inspect
import json
import math
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from services.algos import vendor_decider as vd
from services.algos.portfolio_select import NO_TRADE

ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = ROOT / "scripts" / "algo_backtest" / "vendor_decider_run.py"
ALGO_COUNT = 24
CATEGORIES = ("trend", "range", "volatility", "event")
PLANTED_ALGO = "v00"
PLANTED_CELL = "calm"
PLANTED_MU = 1.0
NOISE_SD = 1.0
CELL_LABELS = ("calm", "nervous")
POOL_MONTHS = 16  # 2025-01 to 2026-04: warm-up, then evaluation from 2025-08


def _weekdays(start: dt.date, months: int) -> list[str]:
    """Every weekday from 'start' for the given number of calendar months."""
    days = []
    day = start
    end_month = (start.year * 12 + start.month - 1) + months
    while (day.year * 12 + day.month - 1) < end_month:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += dt.timedelta(days=1)
    return days


def make_pool(seed: int, months: int = POOL_MONTHS, planted: bool = False):
    """24 algos reporting every weekday, zero-mean noise with an optional planted edge.

    With 'planted', algo PLANTED_ALGO has a mean of PLANTED_MU on days labelled PLANTED_CELL.
    Returns (pool, cell_of_day). Labels are drawn per day from calm and nervous.
    """
    rng = random.Random(seed)
    days = _weekdays(dt.date(2025, 1, 1), months)
    labels = {day: rng.choice(CELL_LABELS) for day in days}
    pool = []
    for index in range(ALGO_COUNT):
        algo = f"v{index:02d}"
        daily = {}
        for day in days:
            mu = (
                PLANTED_MU
                if planted and algo == PLANTED_ALGO and labels[day] == PLANTED_CELL
                else 0.0
            )
            daily[day] = rng.gauss(mu, NOISE_SD)
        pool.append(
            {
                "algo_id": algo,
                "name": f"Vendor {index}",
                "category": CATEGORIES[index % len(CATEGORIES)],
                "live_since": days[0],
                "daily": daily,
            }
        )
    return pool, labels


def _load_run_script():
    spec = importlib.util.spec_from_file_location("vendor_decider_run", RUN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------------------------
# Constants and small helpers
# ---------------------------------------------------------------------------------------------


def test_registered_placeholders_are_the_frozen_values():
    assert vd.TRAILING_MONTHS == 6
    assert vd.MIN_DAYS_PER_CELL == 15
    assert vd.MIN_ELIGIBLE_ALGOS == 6
    assert vd.FIRST_EVAL_MONTH == "2025-08"
    assert vd.LAST_EVAL_MONTH == "2026-10"
    assert vd.CELLS == ("calm", "nervous")
    assert vd.USE_CELLS is True
    assert vd.VIX_MEDIAN_SESSIONS == 60
    assert vd.PASS_MIN_T == 2.0
    assert vd.MIN_EVAL_DAYS == 80
    assert not hasattr(vd, "WARMUP_MONTHS")


def test_live_days_drops_pre_live_dates():
    daily = {"2026-01-30": 1.0, "2026-02-01": 2.0, "2026-02-02": 3.0}
    assert vd.live_days(daily, "2026-02-01") == {"2026-02-01": 2.0, "2026-02-02": 3.0}
    assert vd.live_days(daily, "2026-03-01") == {}


# ---------------------------------------------------------------------------------------------
# The VIX cell
# ---------------------------------------------------------------------------------------------


def test_equal_to_the_median_is_calm_and_above_it_is_nervous():
    earlier = [float(v) for v in range(1, 61)]  # median 30.5
    assert vd.relative_vix_cell(30.5, earlier) == "calm"
    assert vd.relative_vix_cell(30.6, earlier) == "nervous"
    assert vd.relative_vix_cell(30.0, earlier) == "calm"


def test_fewer_than_sixty_earlier_closes_is_unlabelled():
    assert vd.relative_vix_cell(31.0, [float(v) for v in range(1, 60)]) == "unlabelled"
    assert vd.relative_vix_cell(31.0, [float(v) for v in range(1, 61)]) == "nervous"


def test_missing_or_nan_values_are_unlabelled():
    earlier = [float(v) for v in range(1, 61)]
    assert vd.relative_vix_cell(None, earlier) == "unlabelled"
    assert vd.relative_vix_cell(math.nan, earlier) == "unlabelled"
    with_gap = earlier[:10] + [math.nan] + earlier[11:]
    assert vd.relative_vix_cell(31.0, with_gap) == "unlabelled"


def test_only_the_most_recent_sixty_earlier_closes_are_used():
    recent = [float(v) for v in range(1, 61)]
    assert vd.relative_vix_cell(31.0, recent) == vd.relative_vix_cell(31.0, [1000.0] * 40 + recent)


def _vix_series(count: int) -> list[tuple[str, float]]:
    days = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(count)]
    return [(day.isoformat(), 10.0 + (i * 7 % 23)) for i, day in enumerate(days)]


def test_cells_by_day_leaves_the_first_sixty_one_sessions_unlabelled():
    series = _vix_series(80)
    days = [day for day, _ in series]
    cells = vd.cells_by_day(series, days)
    assert all(cells[day] == "unlabelled" for day in days[:61])
    assert all(cells[day] in vd.CELLS for day in days[61:])


def test_cells_by_day_has_no_look_ahead():
    series = _vix_series(90)
    days = [day for day, _ in series]
    before = vd.cells_by_day(series, days)
    # Change the close of a later day and of the session itself: earlier and same-day cells hold.
    changed = list(series)
    changed[70] = (changed[70][0], 999.0)
    after = vd.cells_by_day(changed, days[:70])
    assert all(after[day] == before[day] for day in days[:70])
    own = list(series)
    own[75] = (own[75][0], 999.0)
    assert vd.cells_by_day(own, [days[75]])[days[75]] == before[days[75]]


def test_cells_by_day_uses_only_closes_strictly_before_the_session():
    series = _vix_series(70)
    day = series[65][0]
    cell = vd.cells_by_day(series, [day])[day]
    assert cell == vd.relative_vix_cell(series[64][1], [v for _, v in series[:64]][-60:])


# ---------------------------------------------------------------------------------------------
# Trades, benchmarks and verdicts
# ---------------------------------------------------------------------------------------------


def test_build_trades_uses_the_cells_and_counts_the_unlabelled_days():
    pool = [
        {
            "algo_id": "a",
            "name": "A",
            "category": "trend",
            "live_since": "2026-01-01",
            "daily": {
                "2026-01-05": 0.5,  # calm
                "2026-01-06": -0.5,  # nervous
                "2026-01-07": 1.5,  # unlabelled: dropped
                "2026-01-08": 2.5,  # unlabelled: dropped
                "2025-12-31": 9.0,  # before live_since: not used at all
            },
        }
    ]
    labels = {
        "2026-01-05": "calm",
        "2026-01-06": "nervous",
        "2026-01-07": "unlabelled",
    }
    trades, dropped = vd.build_trades(pool, labels)
    assert [(t["date"], t["cell"], t["net"]) for t in trades] == [
        ("2026-01-05", "calm", 0.5),
        ("2026-01-06", "nervous", -0.5),
    ]
    assert all(t["exit_date"] == t["date"] and t["algo"] == "a" for t in trades)
    assert dropped == {"unlabelled": 2}


def test_use_cells_false_puts_every_day_in_one_cell(monkeypatch):
    monkeypatch.setattr(vd, "USE_CELLS", False)
    pool = [
        {
            "algo_id": "a",
            "name": "A",
            "category": "trend",
            "live_since": "2026-01-01",
            "daily": {"2026-01-05": 1.0, "2026-01-06": 2.0},
        }
    ]
    trades, dropped = vd.build_trades(pool, {"2026-01-05": "unlabelled"})
    assert [t["cell"] for t in trades] == ["all", "all"]
    assert dropped == {"unlabelled": 0}


def test_equal_weight_is_the_mean_of_reporting_algos_per_day():
    trades = [
        {"date": "2026-01-05", "exit_date": "2026-01-05", "algo": "a", "cell": "calm", "net": 1.0},
        {
            "date": "2026-01-05",
            "exit_date": "2026-01-05",
            "algo": "b",
            "cell": "nervous",
            "net": 3.0,
        },
        {"date": "2026-01-06", "exit_date": "2026-01-06", "algo": "a", "cell": "calm", "net": -2.0},
        {"date": "2026-02-02", "exit_date": "2026-02-02", "algo": "a", "cell": "calm", "net": 9.0},
    ]
    series = vd.equal_weight_benchmark(trades, ["2026-01"])
    assert series == [("2026-01-05", 2.0), ("2026-01-06", -2.0)]


def test_warmup_best_holds_the_best_warmup_algo_on_evaluation_days():
    trades = []
    for day in ("2026-01-05", "2026-02-05"):  # warm-up months
        trades.append({"date": day, "exit_date": day, "algo": "a", "cell": "calm", "net": 1.0})
        trades.append({"date": day, "exit_date": day, "algo": "b", "cell": "calm", "net": 0.2})
    trades.append(
        {"date": "2026-03-05", "exit_date": "2026-03-05", "algo": "a", "cell": "calm", "net": -4.0}
    )
    trades.append(
        {"date": "2026-03-06", "exit_date": "2026-03-06", "algo": "b", "cell": "calm", "net": 0.5}
    )
    algo, series = vd.warmup_best_benchmark(trades, "2026-03", ["2026-03"])
    assert algo == "a"
    assert series == [("2026-03-05", -4.0)]


def test_warmup_best_gives_zero_series_when_no_warmup_mean_is_positive():
    trades = [
        {"date": "2026-01-05", "exit_date": "2026-01-05", "algo": "a", "cell": "calm", "net": -1.0},
        {"date": "2026-03-05", "exit_date": "2026-03-05", "algo": "a", "cell": "calm", "net": 5.0},
        {"date": "2026-03-06", "exit_date": "2026-03-06", "algo": "a", "cell": "calm", "net": 2.0},
    ]
    algo, series = vd.warmup_best_benchmark(trades, "2026-02", ["2026-03"])
    assert algo is None
    assert series == [("2026-03-05", 0.0), ("2026-03-06", 0.0)]


def _lines(**overrides):
    values = {
        "eval_days": 100,
        "t_stat": 3.0,
        "positive_halves": True,
        "walk_forward_total": 10.0,
        "equal_weight_total": 1.0,
        "warmup_best_total": 2.0,
    }
    values.update(overrides)
    return vd.verdict_lines(**values)


def test_verdict_passes_when_every_line_is_met():
    assert _lines() == "pass"


def test_verdict_is_inconclusive_under_the_minimum_days():
    assert _lines(eval_days=79) == "inconclusive: too few days"
    assert _lines(eval_days=80, t_stat=3.0) == "pass"


def test_verdict_fails_on_t_statistic_first():
    text = _lines(t_stat=1.99, positive_halves=False, walk_forward_total=0.0)
    assert text.startswith("fail: the t statistic")
    assert "1.99" in text


def test_verdict_fails_when_a_half_is_not_positive():
    text = _lines(positive_halves=False, walk_forward_total=0.0)
    assert text == "fail: the two halves of the period are not both positive."


def test_verdict_fails_when_equal_weight_is_not_beaten():
    text = _lines(walk_forward_total=1.0, equal_weight_total=1.0)
    assert text == "fail: the walk-forward total does not beat following every algo equally."


def test_verdict_fails_when_warmup_best_is_not_beaten():
    text = _lines(walk_forward_total=2.0, warmup_best_total=2.5)
    assert text == "fail: the walk-forward total does not beat the best algo of the warm-up months."


# ---------------------------------------------------------------------------------------------
# Walk-forward behaviour on synthetic pools
# ---------------------------------------------------------------------------------------------


def test_noise_pool_has_no_edge_while_hindsight_looks_positive():
    t_stats = []
    hindsight_positive = 0
    seeds = 100
    for seed in range(seeds):
        pool, labels = make_pool(seed)
        result = vd.evaluate(pool, labels)
        t_stats.append(result["view_b_walk_forward"]["summary"]["t_stat"])
        if result["view_a_hindsight"]["summary"]["net_total"] > 0:
            hindsight_positive += 1
    mean_t = sum(t_stats) / seeds
    assert abs(mean_t) < 0.3, f"mean walk-forward t over {seeds} noise seeds was {mean_t:.3f}"
    assert hindsight_positive / seeds > 0.80, f"hindsight positive on {hindsight_positive}"


def test_planted_edge_is_found_and_beats_both_benchmarks_in_most_seeds():
    seeds = 30
    beats_both = 0
    picked = 0
    picked_total = 0
    for seed in range(seeds):
        pool, labels = make_pool(seed, planted=True)
        result = vd.evaluate(pool, labels)
        picks = result["view_b_walk_forward"]["picks"]
        for month in result["eval_months"]:
            picked_total += 1
            picked += picks[month][PLANTED_CELL] == PLANTED_ALGO
        wf = result["view_b_walk_forward"]["summary"]["net_total"]
        if (
            wf > result["benchmarks"]["equal_weight"]["summary"]["net_total"]
            and wf > result["benchmarks"]["warmup_best"]["summary"]["net_total"]
        ):
            beats_both += 1
    assert picked / picked_total >= 0.80, f"planted algo picked in {picked} of {picked_total}"
    # When the warm-up best algo is the planted one, that benchmark also collects the calm-cell
    # edge, so the comparison turns on the other cell's noise. Hence a majority, not a sweep.
    assert beats_both / seeds > 0.50, f"beat both benchmarks on {beats_both} of {seeds} seeds"


def test_no_look_ahead_a_later_month_changes_no_earlier_pick_or_day():
    pool, labels = make_pool(7)
    before = vd.evaluate(pool, labels)
    last_day = max(labels)
    later = [dict(item, daily=dict(item["daily"])) for item in pool]
    later[0]["daily"][last_day] = 1e9
    after = vd.evaluate(later, labels)

    earlier = [m for m in before["eval_months"] if m != last_day[:7]]
    assert earlier, "need more than one evaluation month"
    for month in earlier:
        picks_before = before["view_b_walk_forward"]["picks"][month]
        assert picks_before == after["view_b_walk_forward"]["picks"][month]

    def earlier_days(result):
        return [row for row in result["view_b_walk_forward"]["days"] if row[0][:7] in earlier]

    assert earlier_days(before) == earlier_days(after)


def test_months_after_the_last_evaluation_month_are_never_read():
    pool, labels = make_pool(5)
    before = vd.evaluate(pool, labels)
    extended = [dict(item, daily=dict(item["daily"])) for item in pool]
    labels_later = dict(labels)
    for item in extended:
        item["daily"]["2026-11-02"] = 1e9
    labels_later["2026-11-02"] = "calm"
    after = vd.evaluate(extended, labels_later)
    assert after["eval_months"] == before["eval_months"]
    assert after["view_b_walk_forward"]["days"] == before["view_b_walk_forward"]["days"]
    assert max(after["eval_months"]) <= vd.LAST_EVAL_MONTH
    assert min(after["eval_months"]) == vd.FIRST_EVAL_MONTH


def test_too_few_algos_in_a_cell_is_no_trade():
    pool, labels = make_pool(2, planted=True)
    five = pool[:5]
    result = vd.evaluate(five, labels)
    assert result["eval_days"] == 0
    assert result["cell_months_no_trade"] == 2 * len(result["eval_months"])
    assert result["verdict"] == "inconclusive: too few days"


def test_six_algos_are_enough_to_trade():
    pool, labels = make_pool(2, planted=True)
    result = vd.evaluate(pool[:6], labels)
    assert result["eval_days"] > 0
    assert result["category_picks"]


def test_evaluation_with_too_little_history_is_inconclusive():
    pool, labels = make_pool(3, months=6)
    result = vd.evaluate(pool, labels)
    assert result["eval_days"] < vd.MIN_EVAL_DAYS
    assert result["verdict"] == "inconclusive: too few days"


def test_evaluate_reports_both_views_benchmarks_and_counts():
    pool, labels = make_pool(11, planted=True)
    result = vd.evaluate(pool, labels)
    assert result["view_a_hindsight"]["label"] == "in-sample, not evidence"
    assert set(result["benchmarks"]) == {"equal_weight", "warmup_best"}
    assert sum(result["category_picks"].values()) > 0
    assert result["cell_months_no_trade"] >= 0
    assert result["dropped_results"] == {"unlabelled": 0}


def test_module_has_no_io_and_no_forbidden_words():
    source = inspect.getsource(vd)
    for word in ("open(", "requests", "sqlite", "datetime.now", "time.time", "eod_library"):
        assert word not in source, f"vendor_decider must not mention {word!r}"
    assert not re.search(r"\barm(ed|ing)?\b", source, re.IGNORECASE)
    assert "paper trading" not in source.lower()
    assert "portfolio_report.verdict" not in source


# ---------------------------------------------------------------------------------------------
# Real input shapes, read through the test hook that skips the freeze checks
# ---------------------------------------------------------------------------------------------


def _write_fixture(root: Path) -> tuple[Path, Path, Path]:
    """Tiny synthetic pool csv, per-day json and data repository in 'root'."""
    repo = root / "data"
    (repo / "context" / "daily").mkdir(parents=True)
    rows = ["timestamp_utc,close"]
    for index, day in enumerate(_weekdays(dt.date(2025, 4, 1), 9)):
        rows.append(f"{day}T03:45:00Z,{10 + index % 7}")
    (repo / "context" / "daily" / "_INDIAVIX.csv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )
    pool = root / "pool.csv"
    pool.write_text(
        "algo_id,name,category,min_capital,live_since,days_with_result\n"
        "v00,Vendor Zero,trend,50000,2025-07-09T04:45:54.282Z,120\n",
        encoding="utf-8",
    )
    daily = root / "daily.json"
    daily.write_text(
        json.dumps(
            {
                "v00": {
                    "name": "Vendor Zero",
                    "performance": {
                        "01/08/2025": 0.5,
                        "04/08/2025": -1.0,
                        "02/08/2025": 3.0,  # a Saturday: not a session, ignored
                        "09/09/2025": 2.0,
                        "01/01/2024": 5.0,  # not in the VIX file: ignored
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return pool, daily, repo


def test_real_input_shapes_are_parsed(tmp_path):
    run = _load_run_script()
    pool_path, daily_path, repo = _write_fixture(tmp_path)
    rows = run.read_pool(pool_path)
    assert rows[0]["live_since"] == "2025-07-09"
    closes = run.vix_closes(repo)
    assert closes[0] == ("2025-04-01", 10.0)
    sessions = {day for day, _ in closes}
    performance = run.read_performance(json.loads(daily_path.read_text(encoding="utf-8")), sessions)
    assert performance == {"v00": {"2025-08-01": 0.5, "2025-08-04": -1.0, "2025-09-09": 2.0}}
    pool = run.build_pool(rows, performance)
    assert pool[0]["daily"] == performance["v00"]


def test_real_input_shapes_run_end_to_end_with_the_hook(tmp_path, capsys):
    run = _load_run_script()
    pool_path, daily_path, repo = _write_fixture(tmp_path)
    code = run.main(
        ["x", str(pool_path), str(daily_path), str(repo)],
        env={},
        _test_hook_bypass_guard_for_synthetic_fixture=True,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert run.NOTICE in out
    assert "Verdict: inconclusive: too few days" in out


def test_real_input_shapes_refuse_a_bad_date_key(tmp_path):
    run = _load_run_script()
    with pytest.raises(ValueError):
        run.read_performance({"v00": {"performance": {"2025-08-01": 1.0}}}, {"2025-08-01"})


# ---------------------------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------------------------

BLOCKED = "This run is blocked until the registration is frozen."
_GIT_ID = [
    "-c",
    "user.name=test",
    "-c",
    "user.email=test@example.com",
    "-c",
    "commit.gpgsign=false",
]
requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is needed for the guard")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *_GIT_ID, *args], capture_output=True, text=True, check=True
    )


def _doc_text(pool_digest: str, frozen: bool = True) -> str:
    mark = "STATUS: FROZEN\n" if frozen else "STATUS: DRAFT\n"
    return f"# registration\n\n{mark}POOL_SHA256: {pool_digest}\n"


def _throwaway_repo(root: Path, run, pool_digest: str, frozen: bool = True) -> str:
    """A temporary repository holding every guarded file, committed once."""
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    for rel in run.GUARDED_PATHS:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{rel} v1\n", encoding="utf-8")
    (root / run.REGISTRATION_DOC).write_text(_doc_text(pool_digest, frozen), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "frozen")
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _write_pool(path: Path) -> str:
    path.write_text(
        "algo_id,name,category,live_since\nv00,Vendor 0,trend,2026-01-01\n", encoding="utf-8"
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


@requires_git
def test_guard_passes_when_nothing_guarded_changed(tmp_path):
    run = _load_run_script()
    sha = _throwaway_repo(tmp_path / "frozen", run, "0" * 64)
    assert run.frozen_check(sha, tmp_path / "frozen") == (True, "")


@requires_git
def test_guard_refuses_without_the_environment_variable(tmp_path, capsys):
    run = _load_run_script()
    code = run.main(["x", "p.csv", "d.json", str(tmp_path)], env={})
    assert code == 2
    assert BLOCKED in capsys.readouterr().out


def test_guard_refuses_a_non_sha_value(tmp_path, capsys):
    run = _load_run_script()
    code = run.main(
        ["x", "p.csv", "d.json", str(tmp_path)], env={"VENDOR_DECIDER_FROZEN": "main; rm"}
    )
    assert code == 2
    assert BLOCKED in capsys.readouterr().out


@requires_git
def test_guard_refuses_a_sha_that_is_not_an_ancestor(tmp_path):
    run = _load_run_script()
    root = tmp_path / "branches"
    frozen_sha = _throwaway_repo(root, run, "0" * 64)
    _git(root, "checkout", "-q", "--orphan", "other")
    _git(root, "commit", "-q", "--allow-empty", "-m", "other branch")
    other_sha = _git(root, "rev-parse", "HEAD").stdout.strip()
    _git(root, "checkout", "-q", frozen_sha)
    ok, why = run.frozen_check(other_sha, root)
    assert ok is False
    assert "not an ancestor" in why


@requires_git
def test_guard_refuses_a_registration_without_the_frozen_line(tmp_path):
    run = _load_run_script()
    sha = _throwaway_repo(tmp_path / "draft", run, "0" * 64, frozen=False)
    ok, why = run.frozen_check(sha, tmp_path / "draft")
    assert ok is False
    assert "STATUS: FROZEN" in why


@requires_git
def test_guard_refuses_a_change_to_any_guarded_file(tmp_path):
    run = _load_run_script()
    for index, rel in enumerate(run.GUARDED_PATHS):
        root = tmp_path / f"case{index}"
        sha = _throwaway_repo(root, run, "0" * 64)
        (root / rel).write_text("changed after the freeze\n", encoding="utf-8")
        _git(root, "commit", "-q", "-am", "change")
        ok, why = run.frozen_check(sha, root)
        assert ok is False, rel
        assert rel in why


@requires_git
def test_guard_ignores_an_unguarded_file(tmp_path):
    run = _load_run_script()
    root = tmp_path / "unguarded"
    sha = _throwaway_repo(root, run, "0" * 64)
    (root / "notes.txt").write_text("not part of the test\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "notes")
    assert run.frozen_check(sha, root) == (True, "")


@requires_git
def test_pool_hash_must_match_the_registered_value(tmp_path):
    run = _load_run_script()
    pool_path = tmp_path / "pool.csv"
    digest = _write_pool(pool_path)
    good = _throwaway_repo(tmp_path / "good", run, digest)
    assert run.pool_check(good, pool_path, tmp_path / "good") == (True, "")

    wrong = _throwaway_repo(tmp_path / "wrong", run, "f" * 64)
    ok, why = run.pool_check(wrong, pool_path, tmp_path / "wrong")
    assert ok is False
    assert "does not match" in why


@requires_git
def test_pool_check_refuses_a_registration_without_a_pool_line(tmp_path):
    run = _load_run_script()
    pool_path = tmp_path / "pool.csv"
    _write_pool(pool_path)
    root = tmp_path / "noline"
    root.mkdir()
    _git(root, "init", "-q")
    for rel in run.GUARDED_PATHS:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("v1\n", encoding="utf-8")
    (root / run.REGISTRATION_DOC).write_text("STATUS: FROZEN\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "no pool line")
    sha = _git(root, "rev-parse", "HEAD").stdout.strip()
    ok, why = run.pool_check(sha, pool_path, root)
    assert ok is False
    assert "POOL_SHA256" in why


def test_run_script_guard_list_names_the_decider_and_harness():
    run = _load_run_script()
    assert run.GUARDED_PATHS == (
        "services/algos/vendor_decider.py",
        "scripts/algo_backtest/vendor_decider_run.py",
        "services/algos/portfolio_select.py",
        "services/algos/portfolio_report.py",
        "services/algos/portfolio_wf.py",
        "docs/algos/vendor-decider-registration-2026-11.md",
    )
    assert run.REGISTRATION_DOC == "docs/algos/vendor-decider-registration-2026-11.md"
    assert NO_TRADE == "no_trade"
