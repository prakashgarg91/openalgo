"""How far below India VIX can real weekly option prices sit before an algo stops paying?

Every Lab result assumes weekly Nifty options are priced at India VIX. VIX is a
30-day measure, and a near-term chain can trade cheaper. A premium seller's edge
shrinks quickly as option prices fall, so this reruns the catalogue algos with
the volatility scaled down, on the full period and the later (test) years.

Usage:
    uv run python scripts/algo_backtest/iv_sensitivity.py <data_dir>
"""

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_data import load_dir  # noqa: E402

from services.algos import lab  # noqa: E402

history = load_dir(sys.argv[1])
SCALES = (1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7)
for algo in ("calm_condor", "zen"):
    print(algo, "(conservative model; option prices as a share of India VIX)")
    for scale in SCALES:
        model = dataclasses.replace(lab.CONSERVATIVE, name=f"iv{scale}", iv_scale=scale)
        lab.MODELS[model.name] = model
        for label, start in (("all ", None), ("test", "2023-01-01")):
            m = lab.run_lab(history, algo, model=model.name, start=start).metrics
            pf = "n/a" if m["profit_factor"] is None else f"{m['profit_factor']:.2f}"
            print(
                f"  {scale:4.2f} {label} n={m['trades']:4d} avg={m['avg']:6.0f} PF={pf:>5s} "
                f"maxDD={m['max_drawdown']:8.0f} gross={m['avg_gross']:6.0f}"
            )
    print()
