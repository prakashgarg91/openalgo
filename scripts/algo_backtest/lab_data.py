"""Load the CSVs written by fetch_history.py as a Lab History."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos.lab import History  # noqa: E402

FILES = {"nifty": "nsei", "vix": "vix", "spx": "spx", "ndx": "ndx", "crude": "crude", "dxy": "dxy"}


def load_dir(data_dir: str) -> History:
    frames = {}
    for key, name in FILES.items():
        df = pd.read_csv(f"{data_dir}/{name}.csv", index_col=0, parse_dates=True)
        df.index = df.index.tz_localize(None) if df.index.tz else df.index
        frames[key] = df
    return History(frames)
