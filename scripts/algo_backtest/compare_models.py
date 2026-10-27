"""How much of each algo's result survives a stricter pricing model?

Runs the regime-gated algos under the standard and the conservative model, over
the full period and split into train (to 2022) and test (2023 on).

Usage:
    uv run python scripts/algo_backtest/compare_models.py <data_dir>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_data import load_dir  # noqa: E402

from services.algos.lab import run_lab  # noqa: E402

history = load_dir(sys.argv[1])
ALGOS = ("zen", "mirror_zen", "calm_condor")
PERIODS = {"all": (None, None), "train": (None, "2022-12-31"), "test": ("2023-01-01", None)}


def line(m):
    if not m["trades"]:
        return "no trades"
    pf = "n/a" if m["profit_factor"] is None else f"{m['profit_factor']:.2f}"
    return (
        f"n={m['trades']:4d} win={m['win_rate']:4.1f}% avg={m['avg']:6.0f} PF={pf:>5s} "
        f"maxDD={m['max_drawdown']:8.0f} | gross={m['avg_gross']:6.0f} cost={m['avg_cost']:5.0f} "
        f"breaks even at Rs {m['break_even_cost']:5.0f}/lot"
    )


for algo in ALGOS:
    print(algo)
    for period, (start, end) in PERIODS.items():
        for model in ("standard", "conservative"):
            m = run_lab(history, algo, model=model, start=start, end=end).metrics
            print(f"  {period:5s} {model:12s} {line(m)}")
    print()
