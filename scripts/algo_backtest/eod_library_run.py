"""The single run of the end-of-day library test (docs/algos/eod-library-registration-DRAFT-2026-11-17.md).

GUARDED. It refuses to run unless:
  - the environment variable EOD_LIBRARY_FROZEN holds a commit sha that is an ancestor of HEAD, and
    that commit's registration document carries the text 'STATUS: FROZEN';
  - none of the guarded files (the library, the run script, the portfolio harness, the regime gate,
    costs, lots, the screen, the national event file and the registration document) differs between
    that commit and HEAD;
  - the national event file docs/algos/eod_library_events.json has a top-level 'complete': true;
  - a refit of the regime model matches the registered constants in services/algos/eod_library.py
    within 1e-4. The refit is only compared, never used.
Otherwise it prints the refusal and exits 2.

When it does run: it reads the NSE end-of-day option table and the context daily files in the data
repository, builds one row per entry session, turns the rows into trades with services.algos.eod_library
(regime groups from the registered constants, effective expiries from the option table), and runs
services.algos.portfolio_wf over the low cell only, from April 2022 (April 2021 to March 2022 is the
warm-up). It prints both views, the best-single-algo benchmark and the verdict. It writes nothing and
places no order.

Usage (only after the freeze):
    EOD_LIBRARY_FROZEN=<sha> uv run python scripts/algo_backtest/eod_library_run.py <data_repo>
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

REGISTRATION_DOC = "docs/algos/eod-library-registration-DRAFT-2026-11-17.md"
EVENTS_FILE = "docs/algos/eod_library_events.json"
FROZEN_MARK = "STATUS: FROZEN"
BLOCKED = "This run is blocked until the registration is frozen."
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
FIRST_EVAL_MONTH = "2022-04"
FIRST_SESSION = "2021-04-01"
STRIKE_STEP = 50
GUARDED_PATHS = (
    "services/algos/eod_library.py",
    "scripts/algo_backtest/eod_library_run.py",
    "services/algos/portfolio_labels.py",
    "services/algos/portfolio_select.py",
    "services/algos/portfolio_report.py",
    "services/algos/portfolio_wf.py",
    "services/algos/regime_gate.py",
    "services/algos/costs.py",
    "services/algos/nse_lots.py",
    "services/algos/eod_screen.py",
    EVENTS_FILE,
    REGISTRATION_DOC,
)


def frozen_check(sha, root=REPO_ROOT):
    """(True, '') when sha is an ancestor of HEAD, its registration carries the frozen mark, and no
    guarded file differs between sha and HEAD. Otherwise (False, why)."""
    if not sha or not SHA_PATTERN.match(sha.strip()):
        return False, "EOD_LIBRARY_FROZEN must be a commit sha."
    sha = sha.strip()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )

    if git("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
        return False, "That sha is not a commit in this repository."
    if git("merge-base", "--is-ancestor", sha, "HEAD").returncode != 0:
        return False, "That sha is not an ancestor of HEAD."
    shown = git("show", f"{sha}:{REGISTRATION_DOC}")
    if shown.returncode != 0 or FROZEN_MARK not in shown.stdout:
        return False, f"The registration at that commit does not carry '{FROZEN_MARK}'."
    changed = git("diff", "--quiet", sha, "HEAD", "--", *GUARDED_PATHS)
    if changed.returncode == 1:
        names = git("diff", "--name-only", sha, "HEAD", "--", *GUARDED_PATHS).stdout.split()
        return False, "Guarded files changed after the freeze: " + ", ".join(names)
    if changed.returncode != 0:
        return False, "Could not compare the frozen commit with HEAD."
    return True, ""


def events_complete(doc):
    """(True, '') when the national event file is marked complete at the top level, else (False, why)."""
    if not isinstance(doc, dict):
        return False, "The national event file is missing or unreadable."
    if doc.get("complete") is not True:
        return False, "The national event list is not complete yet."
    return True, ""


def regime_mismatch(frame):
    """None when a refit on the frame matches the registered regime constants, else the reason.

    The refit is only compared. The grouping always uses the registered constants.
    """
    import numpy as np

    from services.algos import regime_gate
    from services.algos.eod_library import (
        REGIME_COEF_RANGE_1,
        REGIME_COEF_VIX_PREV,
        REGIME_CUTS,
        REGIME_INTERCEPT,
        REGIME_TOLERANCE,
    )

    coef, cuts = regime_gate.fit(frame)
    registered = np.array([REGIME_COEF_VIX_PREV, REGIME_COEF_RANGE_1, REGIME_INTERCEPT])
    if len(coef) != 3 or len(cuts) != len(REGIME_CUTS):
        return "The refit has a different shape from the registered regime model."
    worst = max(
        float(np.max(np.abs(np.asarray(coef) - registered))),
        float(np.max(np.abs(np.asarray(cuts) - np.array(REGIME_CUTS)))),
    )
    if worst > REGIME_TOLERANCE:
        return (
            "The regime refit does not match the registered constants "
            f"(largest difference {worst:.6f}, tolerance {REGIME_TOLERANCE})."
        )
    return None


def _daily(path):
    """Full daily bars indexed by India date (open, high, low, close, UTC-aware index for the gate)."""
    import pandas as pd

    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame[~frame.index.duplicated(keep="last")]
    return frame


def _inputs(repo):
    """(Nifty close by India date, regime frame) from the context daily files."""
    from scripts.algo_backtest import eight_structure_screen as base
    from services.algos import regime_gate

    nifty_ohlc = _daily(repo / "context" / "daily" / "_NSEI.csv")
    vix_ohlc = _daily(repo / "context" / "daily" / "_INDIAVIX.csv")
    nifty_close = base.load_daily(repo / "context" / "daily" / "_NSEI.csv")
    return nifty_close, regime_gate.range_frame(nifty_ohlc, vix_ohlc)


def _option_keys(options):
    """Option rows as (label, day, settle) with dates as 'YYYY-MM-DD' strings, index options only."""
    import pandas as pd

    opt = options[options["instrument"] == "OPTIDX"]
    return pd.DataFrame(
        {
            "label": pd.to_datetime(opt["expiry"]).dt.strftime("%Y-%m-%d"),
            "day": pd.to_datetime(opt["date"]).dt.strftime("%Y-%m-%d"),
            "settle": opt["settle"].astype(float),
        }
    )


def _effective_expiries(keys):
    """label -> effective expiry date, by the rule in eod_library.effective_expiries."""
    from services.algos.eod_library import effective_expiries

    pairs = keys[["label", "day"]].drop_duplicates()
    return effective_expiries(pairs.groupby("label")["day"].apply(list).to_dict())


def _settlements(keys, effective):
    """effective date -> index settlement, read from the rows on that date. None unless every row agrees.

    On an expiry's own date the settle column holds the index settlement, the same on every strike.
    On a moved expiry the rows on the effective date must agree the same way, or the expiry is not
    settled and its trades are dropped as unusable.
    """
    rows = keys[keys["settle"] > 0]
    out = {}
    for (label, day), grp in rows.groupby(["label", "day"])["settle"]:
        values = {round(float(v), 4) for v in grp}
        out[(label, day)] = values.pop() if len(values) == 1 else None
    return {eff: out.get((label, eff)) for label, eff in effective.items()}


def build_day_rows(repo, events_doc):
    """One row per entry session, from the option table and the context daily files. No result is computed here."""
    import pandas as pd

    from scripts.algo_backtest import eight_structure_screen as base
    from services.algos import eod_screen as es
    from services.algos import events, nse_lots
    from services.algos.eod_library import (
        ALGOS,
        leg_price_exit,
        legs_for,
        regime_group,
        usable_event_entries,
    )

    options = base.load_options(repo)
    chain = es.Chain(options)
    keys = _option_keys(options)
    effective = _effective_expiries(keys)
    settle = _settlements(keys, effective)
    expiry_pairs = sorted((pd.Timestamp(eff), label) for label, eff in effective.items())
    nifty_close, frame = _inputs(repo)
    entries = usable_event_entries(events_doc)
    calendar = list(nifty_close.index)
    position = {d: i for i, d in enumerate(calendar)}
    stored = set(chain.sessions)
    start = pd.Timestamp(FIRST_SESSION)
    rows = []
    for day in chain.sessions:
        if day < start or day not in position:
            continue
        i = position[day]
        exit_day = calendar[i + 1] if i + 1 < len(calendar) else None
        window = [(e, label) for e, label in expiry_pairs if 1 <= (e - day).days <= 6]
        expiry, label = min(window, key=lambda p: (p[0] - day).days) if window else (None, None)
        close = nifty_close.get(day)
        lot = nse_lots.nifty_lot(expiry) if expiry is not None else None
        usable = bool(
            expiry is not None
            and exit_day is not None
            and exit_day in stored
            and close is not None
            and close == close
        )
        atm = int(round(float(close) / STRIKE_STEP) * STRIKE_STEP) if close is not None else None
        legs = {}
        if usable:
            settlement = settle.get(f"{expiry:%Y-%m-%d}")
            for algo in ALGOS:
                entry_prices, exit_prices = [], []
                for kind, strike, _side in legs_for(algo, atm):
                    entry_prices.append(chain.close(day, label, kind, strike))
                    close_on_exit = (
                        chain.close(exit_day, label, kind, strike) if exit_day <= expiry else None
                    )
                    exit_prices.append(
                        leg_price_exit(kind, strike, close_on_exit, settlement, expiry, exit_day)
                    )
                legs[algo] = {"entry": entry_prices, "exit": exit_prices}
        vix_prev = frame["vix_prev"].get(day)
        range_1 = frame["range_1"].get(day)
        group = regime_group(vix_prev, range_1)
        rows.append(
            {
                "entry_date": f"{day:%Y-%m-%d}",
                "exit_date": f"{exit_day:%Y-%m-%d}" if exit_day is not None else "",
                "group": group,
                "entry_is_event": events.blocking(day.date(), entries) is not None,
                "exit_is_event": (
                    events.blocking(exit_day.date(), entries) is not None
                    if exit_day is not None
                    else False
                ),
                "atm": atm if usable else None,
                "lot": lot if usable else None,
                "usable": usable,
                "legs": legs,
            }
        )
    return rows


def run_pipeline(repo, events_doc):
    """Every step after the guard: day rows, trades, both views, both cost runs, the benchmark, the verdict.

    The doubled-cost run re-selects: it is a separate walk-forward run on trades priced at doubled
    costs, so every month's pick is made from doubled-cost results, not from the realistic picks.
    """
    from services.algos import portfolio_wf
    from services.algos.eod_library import (
        ALGOS,
        TRADEABLE_CELLS,
        best_single_benchmark,
        build_trades_counted,
    )

    rows = build_day_rows(repo, events_doc)
    trades, counts = build_trades_counted(rows)
    trades_2x, _ = build_trades_counted(rows, doubled=True)
    cells, algos = list(TRADEABLE_CELLS), list(ALGOS)
    run = portfolio_wf.run(trades, cells=cells, algos=algos, first_month=FIRST_EVAL_MONTH)
    run_2x = portfolio_wf.run(trades_2x, cells=cells, algos=algos, first_month=FIRST_EVAL_MONTH)
    benchmark = best_single_benchmark(trades, FIRST_EVAL_MONTH)
    view_b = run["view_b_walk_forward"]
    doubled_net = run_2x["view_b_walk_forward"]["summary"]["net_total"]
    beats = view_b["summary"]["net_total"] > benchmark["net_total"]
    passed = view_b["verdict"] == "eligible for forward shadow" and doubled_net > 0 and beats
    return {
        "counts": counts,
        "run": run,
        "doubled_net": doubled_net,
        "benchmark": benchmark,
        "beats_benchmark": beats,
        "passed": passed,
    }


def _line(summary):
    return (
        f"days={summary['n_trades_days']} net={summary['net_total']:.0f} t={summary['t_stat']:.2f} "
        f"worst_day={summary['worst_day']:.0f} max_drawdown={summary['max_drawdown']:.0f} "
        f"halves_positive={summary['positive_halves']} days_over_cap={summary['days_over_cap']}"
    )


def report(result):
    """Print the result. Counts, view B (judged), view A (not judged), doubled costs, benchmark, verdict."""
    run = result["run"]
    view_b, view_a = run["view_b_walk_forward"], run["view_a_hindsight"]
    bench = result["benchmark"]
    print("Counts (candidates, kept, dropped by reason):", result["counts"])
    print("View B, walk-forward, realistic costs (the only judged view):")
    print("  " + _line(view_b["summary"]))
    print("  Verdict from the harness:", view_b["verdict"])
    print("View A, hindsight, in-sample, not evidence:")
    print("  " + _line(view_a["summary"]))
    print(
        f"Walk-forward net at doubled costs (re-selected): {result['doubled_net']:.0f} (must be above 0)"
    )
    held = bench["held_algo"] or "none (warm-up mean not positive)"
    print(
        f"Benchmark, best single algo held with no gate: {held}, "
        f"net {bench['net_total']:.0f} (warm-up mean per trade {bench['warm_up_mean_per_trade']:.2f})"
    )
    print(
        f"Hindsight maximum, best single algo over the evaluation (not judged): "
        f"{bench['hindsight_algo_not_judged']}, net {bench['hindsight_net_total_not_judged']:.0f}"
    )
    print(f"Full selector view B net beats the benchmark: {result['beats_benchmark']}")
    print("Registration gates: " + ("all met" if result["passed"] else "NOT all met (fail)"))


def main(
    argv,
    *,
    events_path=None,
    _test_hook_bypass_guard_for_synthetic_fixture=False,
):
    """Run the guarded pipeline. The keyword test hook skips every guard check; only the test suite
    passes it, and only with a synthetic fixture repository. Real runs never set it."""
    if not _test_hook_bypass_guard_for_synthetic_fixture:
        sha = os.environ.get("EOD_LIBRARY_FROZEN", "")
        ok, why = frozen_check(sha)
        if not ok:
            print(BLOCKED)
            print(why)
            return 2
    if len(argv) != 2:
        print(__doc__)
        return 1
    repo = Path(argv[1])
    events_file = Path(events_path) if events_path else REPO_ROOT / EVENTS_FILE
    try:
        events_doc = json.loads(events_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        events_doc = None
    if not _test_hook_bypass_guard_for_synthetic_fixture:
        ok, why = events_complete(events_doc)
        if not ok:
            print(BLOCKED)
            print(why)
            return 2
        _nifty_close, frame = _inputs(repo)
        mismatch = regime_mismatch(frame)
        if mismatch is not None:
            print(BLOCKED)
            print(mismatch)
            return 2
    result = run_pipeline(repo, events_doc)
    report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
