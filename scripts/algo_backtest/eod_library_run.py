"""The single run of the end-of-day library test (docs/algos/eod-library-registration-DRAFT-2026-11-17.md).

GUARDED. It refuses to run unless the environment variable EOD_LIBRARY_FROZEN holds a commit sha that
is an ancestor of HEAD, and that commit's tree holds the registration document with the text
'STATUS: FROZEN' (the owner adds that line at freeze). Otherwise it prints the refusal and exits 2.

When it does run: it reads the NSE end-of-day option table and the context daily files in the data
repository, builds one row per entry session, turns the rows into trades with services.algos.eod_library,
and runs services.algos.portfolio_wf over the low cell only, from April 2022 (April 2021 to March 2022
is the warm-up). It prints both views and the verdict. It writes nothing and places no order.

Usage (only after the freeze):
    EOD_LIBRARY_FROZEN=<sha> uv run python scripts/algo_backtest/eod_library_run.py <data_repo>
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

REGISTRATION_DOC = "docs/algos/eod-library-registration-DRAFT-2026-11-17.md"
FROZEN_MARK = "STATUS: FROZEN"
BLOCKED = "This run is blocked until the registration is frozen."
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
FIRST_EVAL_MONTH = "2022-04"
FIRST_SESSION = "2021-04-01"
STRIKE_STEP = 50


def frozen_check(sha, root=REPO_ROOT):
    """(True, '') when sha is an ancestor of HEAD and its tree carries the frozen mark, else (False, why)."""
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
    return True, ""


def _daily(path):
    """Full daily bars indexed by India date (open, high, low, close, UTC-aware index for the gate)."""
    import pandas as pd

    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame[~frame.index.duplicated(keep="last")]
    return frame


def _calendar(nifty_close):
    """The trading calendar the Nifty has a close on, as naive dates."""
    return list(nifty_close.index)


def build_day_rows(repo):
    """One row per entry session, from the option table and the context daily files. No result is computed here."""
    import pandas as pd

    from scripts.algo_backtest import eight_structure_screen as base
    from services.algos import eod_screen as es
    from services.algos import events, nse_lots, regime_gate
    from services.algos.eod_library import ALGOS, leg_price_exit, legs_for

    chain = es.Chain(base.load_options(repo))
    nifty_ohlc = _daily(repo / "context" / "daily" / "_NSEI.csv")
    vix_ohlc = _daily(repo / "context" / "daily" / "_INDIAVIX.csv")
    nifty_close = base.load_daily(repo / "context" / "daily" / "_NSEI.csv")
    frame = regime_gate.range_frame(nifty_ohlc, vix_ohlc)
    coef, cuts = regime_gate.fit(frame)
    group_by_day = regime_gate.groups(frame, coef, cuts)
    entries = events.load()
    calendar = _calendar(nifty_close)
    position = {d: i for i, d in enumerate(calendar)}
    stored = set(chain.sessions)
    start = pd.Timestamp(FIRST_SESSION)
    rows = []
    for day in chain.sessions:
        if day < start or day not in position:
            continue
        i = position[day]
        exit_day = calendar[i + 1] if i + 1 < len(calendar) else None
        expiries = [e for e in chain.expiries if 1 <= (e - day).days <= 6]
        expiry = min(expiries, key=lambda e: (e - day).days) if expiries else None
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
            for algo in ALGOS:
                entry_prices, exit_prices = [], []
                for kind, strike, _side in legs_for(algo, atm):
                    entry_prices.append(chain.close(day, expiry, kind, strike))
                    close_on_exit = (
                        chain.close(exit_day, expiry, kind, strike) if exit_day <= expiry else None
                    )
                    exit_prices.append(
                        leg_price_exit(
                            kind,
                            strike,
                            close_on_exit,
                            chain.final.get(pd.Timestamp(expiry)),
                            expiry,
                            exit_day,
                        )
                    )
                legs[algo] = {"entry": entry_prices, "exit": exit_prices}
        group = group_by_day.get(day)
        rows.append(
            {
                "entry_date": f"{day:%Y-%m-%d}",
                "exit_date": f"{exit_day:%Y-%m-%d}" if exit_day is not None else "",
                "group": int(group) if group is not None and group == group else None,
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


def _line(summary):
    return (
        f"days={summary['n_trades_days']} net={summary['net_total']:.0f} t={summary['t_stat']:.2f} "
        f"worst_day={summary['worst_day']:.0f} max_drawdown={summary['max_drawdown']:.0f} "
        f"halves_positive={summary['positive_halves']} days_over_cap={summary['days_over_cap']}"
    )


def main(argv):
    sha = os.environ.get("EOD_LIBRARY_FROZEN", "")
    ok, why = frozen_check(sha)
    if not ok:
        print(BLOCKED)
        print(why)
        return 2
    if len(argv) != 2:
        print(__doc__)
        return 1

    from services.algos import portfolio_wf
    from services.algos.eod_library import ALGOS, TRADEABLE_CELLS, build_trades_counted

    repo = Path(argv[1])
    rows = build_day_rows(repo)
    trades, counts = build_trades_counted(rows)
    trades_2x, _ = build_trades_counted(rows, doubled=True)
    run = portfolio_wf.run(
        trades, cells=list(TRADEABLE_CELLS), algos=list(ALGOS), first_month=FIRST_EVAL_MONTH
    )
    run_2x = portfolio_wf.run(
        trades_2x, cells=list(TRADEABLE_CELLS), algos=list(ALGOS), first_month=FIRST_EVAL_MONTH
    )
    single = {
        algo: portfolio_wf.run(
            trades, cells=list(TRADEABLE_CELLS), algos=[algo], first_month=FIRST_EVAL_MONTH
        )["view_b_walk_forward"]["summary"]["net_total"]
        for algo in ALGOS
    }
    best_single = max(single.values())
    view_b = run["view_b_walk_forward"]
    view_a = run["view_a_hindsight"]
    doubled_net = run_2x["view_b_walk_forward"]["summary"]["net_total"]
    beats_single = view_b["summary"]["net_total"] > best_single

    print("Counts (candidates, kept, dropped by reason):", counts)
    print("View B, walk-forward, realistic costs (the only judged view):")
    print("  " + _line(view_b["summary"]))
    print("  Verdict from the harness:", view_b["verdict"])
    print("View A, hindsight, in-sample, not evidence:")
    print("  " + _line(view_a["summary"]))
    print(f"Walk-forward net at doubled costs: {doubled_net:.0f} (must be above 0)")
    print("Single-algo walk-forward net totals:", {k: round(v) for k, v in single.items()})
    print(f"Full selector beats the best single algo: {beats_single}")
    passed = view_b["verdict"] == "eligible for forward shadow" and doubled_net > 0 and beats_single
    print("Registration gates: " + ("all met" if passed else "NOT all met (fail)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
