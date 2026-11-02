"""Run the registered volatility-scaled equity and gold rejection screen ONCE (trial 320).

Registration: docs/algos/vol-scaled-etf-registration.md. A second run is refused through three
independent records: the report in the data repository, the marker in this repository, and the marker in
git history. Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/screen_vol_scaled_etf.py <data_repo> [--history db/etf_history]
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from services.algos import etf_ledger as el  # noqa: E402
from services.algos import etf_vol_scaled as vs  # noqa: E402

RUN_MARKER = ROOT / "docs" / "algos" / "vol-scaled-etf-screen-run.txt"


def marker_in_history() -> bool:
    try:
        out = subprocess.run(
            ["git", "log", "--all", "--oneline", "--", str(RUN_MARKER)],
            capture_output=True, text=True, timeout=30, cwd=ROOT,
        )  # fmt: skip
        return bool(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def refusal(today: date, report_exists: bool, marker_committed: bool) -> str | None:
    """Why the screen must not run, in words for the trader, or None if it may."""
    if report_exists or marker_committed or RUN_MARKER.exists():
        return "This screen has already been run. A second look is a new idea and a new trial. Nothing was run."
    return None


def load_vix(path: Path) -> pd.Series:
    df = pd.read_csv(path)
    day = (
        pd.to_datetime(df["timestamp_utc"], utc=True)
        .dt.tz_convert("Asia/Kolkata")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    return (
        pd.Series(df["close"].to_numpy(dtype=float), index=pd.DatetimeIndex(day))
        .groupby(level=0)
        .last()
    )


def load_closes(history: Path) -> pd.DataFrame:
    frames = {
        name: pd.read_csv(history / f"{stem}.csv", index_col=0, parse_dates=True)["Close"]
        for name, stem in ((el.NIFTY, "niftybees"), (el.GOLD, "goldbees"))
    }
    return pd.DataFrame(frames).dropna()


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    data_repo = Path(args[0])
    history = ROOT / "db" / "etf_history"
    if "--history" in sys.argv:
        history = Path(sys.argv[sys.argv.index("--history") + 1])
    out_dir = data_repo / "research" / "vol_scaled_etf"
    report_path = out_dir / "report.json"
    why = refusal(date.today(), report_path.exists(), marker_in_history())
    if why:
        print(why)
        return 2
    closes = load_closes(history)
    vix = load_vix(data_repo / "context" / "daily" / "_INDIAVIX.csv")
    result = vs.run_screen(closes, vix)
    result["data"] = {
        "first_session": str(closes.index[0].date()),
        "last_session": str(closes.index[-1].date()),
        "vix_last": str(vix.index[-1].date()),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")
    RUN_MARKER.write_text(
        f"Volatility-scaled equity and gold screen (trial 320) was run on {date.today()}.\n"
        f"Verdict: {result['verdict']}. Do not run it again; a second look is a new trial.\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
