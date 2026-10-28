"""Download daily history for the Nifty, gold, bank and junior Nifty ETFs from Yahoo.

Usage: uv run python scripts/algo_backtest/fetch_etf.py <out_dir>
Writes niftybees.csv, goldbees.csv, bankbees.csv, juniorbees.csv (Open and Close, about 15 years).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import lab, universe  # noqa: E402

SYMBOLS = {
    "niftybees": "NIFTYBEES.NS",
    "goldbees": "GOLDBEES.NS",
    "bankbees": "BANKBEES.NS",
    "juniorbees": "JUNIORBEES.NS",
}


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    lab.HISTORY_RANGE = "15y"
    for name, symbol in SYMBOLS.items():
        df = universe.clean(lab._fetch_series(symbol))
        df.to_csv(out / f"{name}.csv")
        print(f"{symbol:14s} {len(df):5d} days {df.index[0].date()} to {df.index[-1].date()}")


if __name__ == "__main__":
    main()
