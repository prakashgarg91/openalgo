"""How the winner earned it: by year, against buy and hold, its neighbours, and the gold dependence.

Usage: uv run python scripts/algo_backtest/universe_detail.py <etf_dir>
"""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import universe_search as us  # noqa: E402

from services.algos import mandate, universe  # noqa: E402

bars = us.load(Path(sys.argv[1]))
idx = bars["equity"].index
warm = universe.WARMUP
rules = {
    "dual_momentum(126, best)": universe.strat("dual_momentum", lookback=126, mode="best"),
    "dual_momentum(63, best)": universe.strat("dual_momentum", lookback=63, mode="best"),
    "dual_momentum(252, best)": universe.strat("dual_momentum", lookback=252, mode="best"),
    "dual_momentum(126, all)": universe.strat("dual_momentum", lookback=126, mode="all"),
    "trend(200) equity only": universe.strat("trend", n=200),
}
runs = {k: universe.run(s, bars)[warm:] for k, s in rules.items()}
runs["buy and hold Nifty ETF"] = universe.buy_and_hold(bars, "equity")[warm:]
runs["buy and hold gold ETF"] = universe.buy_and_hold(bars, "gold")[warm:]
runs["cash (6%)"] = universe.cash_only(idx)[warm:]

years = sorted({d["date"][:4] for d in runs["cash (6%)"]})
print("Total rupees by year on a Rs 1,00,000 base (not compounded)")
print(f"{'':28s}" + "".join(f"{y:>9s}" for y in years))
for name, days in runs.items():
    by = defaultdict(float)
    for d in days:
        by[d["date"][:4]] += d["pnl"]
    print(f"{name:28s}" + "".join(f"{by[y]:9.0f}" for y in years))

print("\nWhole period, Rs 1,00,000 account, one position at a time")
for name, days in runs.items():
    s = mandate.simulate(days, mandate.ONE_LAKH, 1)
    print(
        f"{name:28s} ended {s['final_equity']:9.0f} ({s['return_pct']:+7.1f}%) worst day {s['worst_day']:8.0f} "
        f"deepest fall {s['max_drawdown']:8.0f} ({s['max_drawdown_pct']:.0f}%) within Rs 20,000 cap={s['within_daily_cap']}"
    )

winner = universe.run(rules["dual_momentum(126, best)"], bars)
held = universe.held_dual_momentum(bars, 126, "best").reindex(idx).fillna(0.0)
changes = int((held.diff().abs().sum(axis=1) > 0).sum())
share = {k: round(float(held[k][warm:].mean()) * 100, 1) for k in ("equity", "gold")}
print(
    f"\nWinner position changes: {changes} in {len(idx) / 252:.1f} years; time in Nifty ETF {share['equity']}%, gold ETF {share['gold']}%, cash {round(100 - sum(share.values()), 1)}%"
)
total_cost = 0.0
prev = {"equity": 0.0, "gold": 0.0}
for t in range(len(idx) - 1):
    for k in ("equity", "gold"):
        delta = float(held[k].iloc[t]) - prev[k]
        if abs(delta) > 1e-9:
            total_cost += universe.DEFAULT_COSTS.side(
                abs(delta) * universe.BASE, buy=delta > 0, intraday=False
            )
        prev[k] = float(held[k].iloc[t])
print(f"Costs paid over the whole period: Rs {total_cost:,.0f} (already inside every figure above)")
