"""Summarise the saved bid and ask snapshots: the quoted spread by moment and distance from the money.

Usage:
    uv run python scripts/algo_backtest/summarize_bidask.py <data_repo>
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services import bidask_snapshot as bs  # noqa: E402


def main() -> int:
    files = sorted((Path(sys.argv[1]) / "bidask").glob("*.csv"))
    if not files:
        print("No snapshots yet.")
        return 1
    frame = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    days = frame["stamp"].str[:10].nunique()
    print(f"{len(frame)} quotes over {days} days")
    print(bs.summarize(frame).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    if days < 60:
        print(f"Only {days} of the about 60 days needed to settle the slippage assumption.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
