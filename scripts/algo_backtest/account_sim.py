"""Run the catalogue algos through a Rs 1,00,000 account (one lot, Rs 20,000 daily cap) on real option prices.

Usage: uv run python scripts/algo_backtest/account_sim.py <history_dir> <real_options_dir>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_data import load_dir  # noqa: E402

from services.algos import lab, mandate  # noqa: E402

H = load_dir(sys.argv[1])
R = lab.load_real_prices(Path(sys.argv[2]))
A = mandate.ONE_LAKH


def show(label, trades, start="2022-01-01"):
    t = [x for x in trades if x["date"] >= start]
    s = mandate.simulate(t, A, 1)
    print(
        f"{label:34s} trades={s['days_traded']:4d} ended={s['final_equity']:9.0f} ({s['return_pct']:+6.1f}%) worst day={s['worst_day']:8.0f} deepest fall={s['max_drawdown']:9.0f} ({s['max_drawdown_pct']:.0f}%) cap kept={s['within_daily_cap']} wiped={s['ruined']}"
    )


print("Rs 1,00,000, one lot, real option prices 2022-01 to 2026-10, cautious costs")
zen = lab.run_lab(H, "zen", model="conservative", real=R).trades
show("Zen (all days it trades)", zen)
show("  Zen, bullish days only", [t for t in zen if t["side"] == "bull_put"])
show("  Zen, bearish days only", [t for t in zen if t["side"] == "bear_call"])
show("Mirror Zen", lab.run_lab(H, "mirror_zen", model="conservative", real=R).trades)
show("Calm Condor", lab.run_lab(H, "calm_condor", model="conservative", real=R).trades)
show("Do nothing", [])
print("\nSame account, MODEL prices 2022-01 to 2026-10 (flatters sellers), for contrast")
show("Zen (model prices)", lab.run_lab(H, "zen", model="conservative").trades)
print("\nZen by year, real prices, per lot:")
import collections

by = collections.defaultdict(list)
for t in zen:
    by[t["date"][:4]].append(t["pnl"])
for y in sorted(by):
    print(f"  {y}: n={len(by[y]):3d} total={sum(by[y]):8.0f} avg={sum(by[y]) / len(by[y]):6.0f}")
