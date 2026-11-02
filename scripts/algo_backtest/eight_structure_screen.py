"""Run the registered eight-structure rejection screen (docs/algos/eight-structure-screen-registration.md).

Registered on 2 November 2026 to be run ONCE, on or after 1 December 2026, on the NSE end-of-day data in
the private data repository. ``--check`` only counts what data and documented lot sizes are there and
evaluates no price, so it is safe to run at any time. A full run refuses to start before 1 December 2026
and refuses a second run. Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/eight_structure_screen.py <data_repo> [--check]
"""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import eod_screen as es  # noqa: E402
from services.algos import nse_lots  # noqa: E402

RUN_NOT_BEFORE = date(2026, 12, 1)
#: Written into the repository when the screen has run, so a fresh clone of the data cannot run it again.
RUN_MARKER = (
    Path(__file__).resolve().parents[2] / "docs" / "algos" / "eight-structure-screen-run.txt"
)
PRIMARY = (pd.Timestamp("2021-04-01"), pd.Timestamp("2024-09-26"))
OVERLAP = (pd.Timestamp("2024-10-03"), pd.Timestamp("2026-10-27"))
RUNNING_COUNT_AFTER = 319


def marker_in_history() -> bool:
    """True if the run marker was ever committed in this repository (best effort, any branch)."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "log", "--all", "--oneline", "--", str(RUN_MARKER)],
            capture_output=True, text=True, timeout=30, cwd=RUN_MARKER.parents[2],
        )  # fmt: skip
        return bool(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def refusal(today: date, report_exists: bool) -> str | None:
    """Why the screen must not run now, in words for the trader, or None if it may."""
    if today < RUN_NOT_BEFORE:
        return (
            "This screen is registered to run once, on or after 1 December 2026. Nothing was run."
        )
    if report_exists:
        return "This screen has already been run. A second look is a new idea and a new trial. Nothing was run."
    return None


def load_daily(path: Path) -> pd.Series:
    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index, utc=True)
    close = frame["close"]
    close.index = pd.DatetimeIndex(
        close.index.tz_convert("Asia/Kolkata").tz_localize(None)
    ).normalize()
    return close[~close.index.duplicated(keep="last")]


def load_options(repo: Path) -> pd.DataFrame:
    frames = [pd.read_csv(f) for f in sorted((repo / "nse_fo_eod").glob("nifty_fo_*.csv.gz"))]
    return pd.concat(frames, ignore_index=True)


def check(chain: es.Chain, nifty: pd.Series, vix: pd.Series) -> None:
    print(f"{len(chain.sessions)} stored sessions, {len(chain.expiries)} expiries")
    for label, (a, b) in (("primary", PRIMARY), ("overlap", OVERLAP)):
        for cadence in ("weekly", "monthly"):
            days = [e for e in es.cadence_expiries(chain, cadence) if a <= e <= b]
            documented = [e for e in days if nse_lots.nifty_lot(e) is not None]
            print(
                f"  {label} {cadence}: {len(days)} expiries, {len(documented)} with a documented lot"
            )
    undocumented = [e for e in chain.expiries if nse_lots.nifty_lot(e) is None]
    print(f"  expiries before the first documented lot (excluded): {len(undocumented)}")
    print(f"  Nifty close {nifty.index.min():%Y-%m-%d} to {nifty.index.max():%Y-%m-%d}; "
          f"India VIX {vix.index.min():%Y-%m-%d} to {vix.index.max():%Y-%m-%d}")  # fmt: skip
    print("No price was evaluated. The screen itself runs once, on or after 1 December 2026.")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    repo = Path(args[0])
    out_dir = repo / "research" / "eight_structure_screen"
    if "--check" not in sys.argv:
        why = refusal(
            date.today(),
            (out_dir / "report.json").exists() or RUN_MARKER.exists() or marker_in_history(),
        )
        if why:
            print(why)
            return 2
    chain = es.Chain(load_options(repo))
    nifty = load_daily(repo / "context" / "daily" / "_NSEI.csv")
    vix = load_daily(repo / "context" / "daily" / "_INDIAVIX.csv")
    if "--check" in sys.argv:
        check(chain, nifty, vix)
        return 0
    sessions = chain.sessions
    report: dict = {
        "trials_added": 8,
        "running_count": RUNNING_COUNT_AFTER,
        "primary": {},
        "overlap": {},
    }
    for name, spec in es.SPECS.items():
        for label, (a, b) in (("primary", PRIMARY), ("overlap", OVERLAP)):
            result = es.simulate(spec, chain, nifty, vix, nse_lots.nifty_lot, a, b)
            one = es.evaluate(result, spec.cadence, sessions)
            # Keep everything: the screen runs once, so what is not saved now cannot be read later.
            one["rows"] = es.trade_rows(result)
            one["net_by_trailing_market"] = es.net_by_trailing_market(result.trades, nifty)
            report[label][name] = one
    report["control_suspect"] = es.control_is_suspect(report["primary"])
    # If the control passed, the data or the costs are suspect: name no survivors.
    report["survivors"] = (
        [] if report["control_suspect"] else es.choose_survivors(report["primary"])
    )
    report["lost_money_in_primary"] = sorted(
        n for n, r in report["primary"].items() if r["stats"]["net"] < 0
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    RUN_MARKER.write_text(
        f"The eight-structure screen was run on {date.today()}. Commit this file. It stays so the screen "
        "cannot be run a second time from another copy of the data.\n",
        encoding="utf-8",
    )
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    if report["control_suspect"]:
        print(
            "The control (long straddle) passed. Stop: check the data and the cost code before reading "
            "anything else. No survivors were named."
        )
    print(
        json.dumps(
            {k: report[k] for k in ("survivors", "control_suspect", "lost_money_in_primary")},
            indent=2,
        )
    )
    for name, r in report["primary"].items():
        s = r["stats"]
        print(f"  {name}: {s['trades']} trades, net {s['net']:,.0f}, at twice costs {s['net_2x']:,.0f}, "
              f"drawdown {s['drawdown']:,.0f}, verdict {r['verdict']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
