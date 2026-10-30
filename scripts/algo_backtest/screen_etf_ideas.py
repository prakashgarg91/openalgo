"""Screen the registered ETF ideas 1 to 3 on the 15-year ETF history. SCREENING ONLY, never a verdict.

The history in db/etf_history/ has already been looked at (docs/algos/idea-registration.md calls it
development data), so a pass here confirms nothing. It shows whether the ledger code runs on 15 years,
how large each idea's fall and worst day are, and whether the idea is worth watching forward.

Usage:
    uv run python scripts/algo_backtest/fetch_etf.py db/etf_history      # once
    uv run python scripts/algo_backtest/screen_etf_ideas.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import etf_ledger as el  # noqa: E402

HISTORY = Path(__file__).resolve().parents[2] / "db" / "etf_history"
WARMUP = 300


def main() -> int:
    files = [HISTORY / "niftybees.csv", HISTORY / "goldbees.csv"]
    if not all(f.exists() for f in files):
        print("No ETF history. Run scripts/algo_backtest/fetch_etf.py db/etf_history first.")
        return 1
    closes = pd.DataFrame(
        {
            n: pd.read_csv(f, index_col=0, parse_dates=True)["Close"]
            for n, f in zip((el.NIFTY, el.GOLD), files, strict=True)
        }
    ).dropna()
    start = str(closes.index[WARMUP].date())
    weights = {i: el.average_weights(el.run_ledger(i, closes, start).rows) for i in el.all_rules()}
    ledgers = el.run_all(closes, start, weights)
    years = (closes.index[-1] - pd.Timestamp(start)).days / 365.25
    print(
        f"Screening {start} to {closes.index[-1].date()} ({years:.1f} years, development data, NOT a test)"
    )
    print(
        f"{"ledger":34s} {'CAGR':>6s} {'end Rs':>9s} {'deepest fall':>12s} {'worst day':>10s} {'costs':>7s}"
    )
    for key, led in ledgers.items():
        if not key.endswith(":base"):
            continue
        r = led.rows
        end = float(r["nav"].iloc[-1])
        print(
            f"{key[:-5]:34s} {((end / el.CAPITAL) ** (1 / years) - 1) * 100:5.1f}% {end:9,.0f} "
            f"{r['drawdown'].max():12,.0f} {r['daily_pnl'].min():10,.0f} {r['cumulative_cost'].iloc[-1]:7,.0f}"
        )
    print("Doubled costs, ending value:")
    for key, led in ledgers.items():
        if key.endswith(":double"):
            print(f"  {key[:-7]:30s} Rs {float(led.rows['nav'].iloc[-1]):9,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
