"""The single run of the vendor decider test (docs/algos/vendor-decider-registration-2026-11.md).

GUARDED. It refuses to run unless:
  - the environment variable VENDOR_DECIDER_FROZEN holds a commit sha that is an ancestor of HEAD,
    and that commit's registration document carries the text 'STATUS: FROZEN';
  - none of the guarded files (the decider, this script, the portfolio selector and harness, and
    the registration document) differs between that commit and HEAD;
  - the pool csv's sha256 equals the value written at that commit as 'POOL_SHA256: <hex>'.
Otherwise it prints the refusal and exits 2.

When it does run: it reads the vendor pool csv (columns algo_id, name, category, live_since, and
others that are ignored; live_since may be a date-time, only its date is used), and the per-day json
{algo_id: {'name': ..., 'performance': {'DD/MM/YYYY': percent}}}. Result dates that are not
sessions in the data repository's India VIX file are ignored. Each day's cell comes from the VIX
closes (context/daily/_INDIAVIX.csv, dates in Asia/Kolkata). It calls
services.algos.vendor_decider.evaluate, prints the results, and writes nothing. It places no order.

Usage (only after the freeze):
    VENDOR_DECIDER_FROZEN=<sha> uv run python scripts/algo_backtest/vendor_decider_run.py <pool.csv> <daily.json> <data_repo>
"""

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

REGISTRATION_DOC = "docs/algos/vendor-decider-registration-2026-11.md"
FROZEN_MARK = "STATUS: FROZEN"
POOL_MARK = re.compile(r"^POOL_SHA256:\s*([0-9a-fA-F]{64})\s*$", re.MULTILINE)
BLOCKED = "This run is blocked until the registration is frozen."
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
GUARDED_PATHS = (
    "services/algos/vendor_decider.py",
    "scripts/algo_backtest/vendor_decider_run.py",
    "services/algos/portfolio_select.py",
    "services/algos/portfolio_report.py",
    "services/algos/portfolio_wf.py",
    REGISTRATION_DOC,
)
POOL_COLUMNS = ("algo_id", "name", "category", "live_since")
VIX_FILE = "context/daily/_INDIAVIX.csv"
NOTICE = (
    "Results are percent points of each algo's own maximum allocation, as shown by the vendor; "
    "they are the vendor's reported figures, not ours, and exclude our own costs."
)


def frozen_check(sha, root=REPO_ROOT):
    """(True, '') when sha is an ancestor of HEAD, its registration carries the frozen mark, and no
    guarded file differs between sha and HEAD. Otherwise (False, why)."""
    if not sha or not SHA_PATTERN.match(sha.strip()):
        return False, "VENDOR_DECIDER_FROZEN must be a commit sha."
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


def pool_check(sha, pool_path, root=REPO_ROOT):
    """(True, '') when the pool csv's sha256 is the POOL_SHA256 written at sha, else (False, why)."""
    shown = subprocess.run(
        ["git", "-C", str(root), "show", f"{sha.strip()}:{REGISTRATION_DOC}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if shown.returncode != 0:
        return False, "The registration at that commit could not be read."
    match = POOL_MARK.search(shown.stdout)
    if match is None:
        return False, "The registration at that commit gives no POOL_SHA256 line."
    try:
        digest = hashlib.sha256(Path(pool_path).read_bytes()).hexdigest()
    except OSError:
        return False, "The pool file could not be read."
    if digest != match.group(1).lower():
        return False, "The pool file's sha256 does not match the POOL_SHA256 in the registration."
    return True, ""


def read_pool(pool_path):
    """Pool rows as dicts with algo_id, name, category and live_since ('YYYY-MM-DD').

    live_since may be a date-time such as 2025-07-09T04:45:54.282Z; only its date is kept.
    Raises ValueError when a column is missing or a live_since date does not parse.
    """
    with open(pool_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not set(POOL_COLUMNS) <= set(reader.fieldnames):
            raise ValueError("The pool csv must have the columns " + ", ".join(POOL_COLUMNS) + ".")
        rows = []
        for row in reader:
            live = date.fromisoformat(row["live_since"][:10]).isoformat()
            rows.append({**row, "live_since": live})
    return rows


def read_performance(doc, sessions):
    """{algo_id: {'YYYY-MM-DD': percent}} from the per-day json, keeping only VIX sessions.

    Each entry is {'name': ..., 'performance': {'DD/MM/YYYY': number}}. Null values are skipped.
    Raises ValueError for a date key that is not DD/MM/YYYY.
    """
    out = {}
    for algo_id, entry in doc.items():
        days = {}
        for key, value in (entry.get("performance") or {}).items():
            iso = datetime.strptime(key, "%d/%m/%Y").date().isoformat()
            if value is None or iso not in sessions:
                continue
            days[iso] = float(value)
        out[algo_id] = days
    return out


def vix_closes(repo):
    """(ISO date, India VIX close) pairs from the data repository, dates in Asia/Kolkata, oldest first."""
    import pandas as pd

    frame = pd.read_csv(Path(repo) / VIX_FILE, index_col=0)
    frame.index = (
        pd.to_datetime(frame.index, utc=True)
        .tz_convert("Asia/Kolkata")
        .tz_localize(None)
        .normalize()
    )
    closes = frame["close"][~frame.index.duplicated(keep="last")].sort_index()
    return [(day.strftime("%Y-%m-%d"), float(value)) for day, value in closes.items()]


def build_pool(rows, performance):
    """Pool items for services.algos.vendor_decider. Raises ValueError for a pool algo with no results."""
    pool = []
    for row in rows:
        algo_id = row["algo_id"]
        if algo_id not in performance:
            raise ValueError(f"No performance results for pool algo '{algo_id}'.")
        pool.append(
            {
                "algo_id": algo_id,
                "name": row["name"],
                "category": row["category"],
                "live_since": row["live_since"],
                "daily": performance[algo_id],
            }
        )
    return pool


def _monthly_positive(days):
    """(months with a positive total, months in all) for a (date, net) series."""
    totals = defaultdict(float)
    for day, net in days:
        totals[day[:7]] += net
    return sum(1 for total in totals.values() if total > 0), len(totals)


def _line(summary, days):
    positive, months = _monthly_positive(days)
    return (
        f"total {summary['net_total']:.4f}, mean per day {summary['mean_per_trading_day']:.4f}, "
        f"t {summary['t_stat']:.2f}, positive months {positive} of {months}, "
        f"both halves positive {summary['positive_halves']}, days {summary['n_trades_days']}"
    )


def report(result, names):
    """Print the notice, both views, both benchmarks, picks, counts and the verdict."""
    from services.algos.portfolio_select import NO_TRADE

    view_b = result["view_b_walk_forward"]
    view_a = result["view_a_hindsight"]
    bench = result["benchmarks"]
    print(NOTICE)
    print(f"Evaluation months: {', '.join(result['eval_months']) or 'none'}")
    print("View B, walk-forward (the only judged view):")
    print("  " + _line(view_b["summary"], view_b["days"]))
    print(f"View A, hindsight, {view_a['label']}:")
    print("  " + _line(view_a["summary"], view_a["days"]))
    eq = bench["equal_weight"]
    print("Benchmark, follow every algo equally:")
    print("  " + _line(eq["summary"], eq["days"]))
    warm = bench["warmup_best"]
    held = f"{warm['algo']} ({names.get(warm['algo'], '')})" if warm["algo"] else "none"
    print(f"Benchmark, warm-up best algo held: {held}")
    print("  " + _line(warm["summary"], warm["days"]))
    print("Picks per month (algo id and name):")
    for month in result["eval_months"]:
        parts = []
        for cell, pick in view_b["picks"][month].items():
            label = "no trade" if pick == NO_TRADE else f"{pick} {names.get(pick, '')}".strip()
            parts.append(f"{cell}: {label}")
        print(f"  {month}  " + "; ".join(parts))
    print("Picks by category (month x cell):", result["category_picks"])
    print(f"No-trade cell-months: {result['cell_months_no_trade']}")
    print("Dropped algo-day results (unlabelled day, no VIX cell):", result["dropped_results"])
    print("Verdict:", result["verdict"])


def main(argv, *, env=None, _test_hook_bypass_guard_for_synthetic_fixture=False):
    """Run the guarded decider. Returns the process exit code.

    The keyword test hook skips the freeze and pool-hash checks. Only the test suite passes it,
    and only with synthetic files in a temporary directory. Real runs never set it.
    """
    env = os.environ if env is None else env
    sha = env.get("VENDOR_DECIDER_FROZEN", "")
    pool_path_arg = argv[1] if len(argv) > 1 else ""
    if not _test_hook_bypass_guard_for_synthetic_fixture:
        ok, why = frozen_check(sha)
        if not ok:
            print(BLOCKED)
            print(why)
            return 2
    if len(argv) != 4:
        print(__doc__)
        return 1
    pool_path, daily_path, repo = Path(pool_path_arg), Path(argv[2]), Path(argv[3])
    if not _test_hook_bypass_guard_for_synthetic_fixture:
        ok, why = pool_check(sha, pool_path)
        if not ok:
            print(BLOCKED)
            print(why)
            return 2

    from services.algos import vendor_decider

    try:
        rows = read_pool(pool_path)
        doc = json.loads(daily_path.read_text(encoding="utf-8"))
        closes = vix_closes(repo)
        sessions = {day for day, _ in closes}
        performance = read_performance(doc, sessions)
        pool = build_pool(rows, performance)
    except (OSError, ValueError, KeyError) as exc:
        print(BLOCKED)
        print(f"The pool, the daily results or the VIX file could not be read: {exc}")
        return 2

    days = sorted({day for item in pool for day in item["daily"]})
    cell_of_day = vix_cells(closes, days)
    result = vendor_decider.evaluate(pool, cell_of_day)
    report(result, {item["algo_id"]: item["name"] for item in pool})
    return 0


def vix_cells(closes, days):
    """Cell for each result date, from the VIX closes before it (see vendor_decider.cells_by_day)."""
    from services.algos import vendor_decider

    return vendor_decider.cells_by_day(closes, days)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
