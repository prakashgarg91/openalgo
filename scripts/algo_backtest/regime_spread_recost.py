"""Re-cost the regime-gated spread test under the registered retail-realistic scenario.

Docs: docs/algos/cost-scenario-registration.md. The trades are the same ones the regime test
produced (cost is not part of any decision); only each trade's cost is recomputed. Read only;
places no order.

Usage:
    uv run python scripts/algo_backtest/regime_spread_recost.py <data_repo>
"""

import copy
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.algo_backtest import regime_spread_study as rs  # noqa: E402
from services.algos import forward_shadow as fs  # noqa: E402
from services.algos import regime_gate as rg  # noqa: E402
from services.algos.costs import realistic_cost  # noqa: E402


def recost(result: fs.ShadowResult) -> tuple[fs.ShadowResult, float]:
    """A copy of the result with every trade's net recomputed, and the total realistic cost."""
    out = copy.copy(result)
    out.trades = []
    total = 0.0
    for t in result.trades:
        c = realistic_cost(
            t["entry"], t["exit"], t["entry_s"], t["entry_l"], t["exit_s"], t["exit_l"], t["lot"]
        )
        total += c
        out.trades.append({**t, "cost": c, "net": t["pts"] * t["lot"] - c})
    return out, total


def metrics(result: fs.ShadowResult, days: list[pd.Timestamp]) -> dict:
    cons_net = float(sum(t["net"] for t in result.trades))
    cons_cost = float(sum(t["cost"] for t in result.trades))
    real, real_cost = recost(result)
    real_net = float(sum(t["net"] for t in real.trades))
    paths = fs.equity_paths(real, days)
    return {
        "episodes": fs.episodes_closed(result),
        "trades": len(result.trades),
        "conservative_net": round(cons_net),
        "conservative_cost": round(cons_cost),
        "realistic_net": round(real_net),
        "realistic_net_2x": round(real_net - real_cost),
        "realistic_cost": round(real_cost),
        "realistic_drawdown": round(fs.max_drawdown(paths)),
        "realistic_worst_day": round(fs.worst_day(paths)),
        "pre_cost_net": round(float(sum(t["pts"] * t["lot"] for t in result.trades))),
    }


def main() -> int:
    repo = Path(sys.argv[1])
    nifty = rs.read_daily(repo / "context" / "daily" / "_NSEI.csv")
    vix_bars = rs.read_daily(repo / "context" / "daily" / "_INDIAVIX.csv")
    frame = rg.range_frame(nifty, vix_bars)
    coef, cuts = rg.fit(frame)
    grp = rg.groups(frame, coef, cuts)
    out: dict = {"selection": {}, "held_out": {}}
    with tempfile.TemporaryDirectory() as scratch:
        bars, _ = rs.load_bars(repo, Path(scratch))
        index, vix = rs.load_index(repo), rs.load_vix(repo)
        days = bars.days()
        cut = days[2 * len(days) // 3 - 1]
        sel_days = [d for d in days if d <= cut]
        held_days = [d for d in days if d > cut]
        for side in rs.SIDES:
            for gate in rg.GATES:
                key = f"{side}_{gate}"
                out["selection"][key] = metrics(
                    rs.run_cell(side, gate, bars, index, vix, sel_days, grp), sel_days
                )
        ok = {
            k: v
            for k, v in out["selection"].items()
            if v["episodes"] >= rs.MIN_SELECT_EPISODES and v["realistic_net_2x"] > 0
        }
        out["selected"] = max(ok, key=lambda k: ok[k]["realistic_net"]) if ok else None
        (repo / "research" / "regime_spread" / "recost_selection.json").write_text(
            json.dumps(out, indent=2), encoding="utf-8"
        )
        print(f"selection written; qualifying cells: {len(ok)}; selected: {out['selected']}")
        for side in rs.SIDES:
            for gate in rg.GATES:
                key = f"{side}_{gate}"
                out["held_out"][key] = metrics(
                    rs.run_cell(side, gate, bars, index, vix, held_days, grp), held_days
                )
    (repo / "research" / "regime_spread" / "recost.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )
    print(
        f"{'cell':8} {'period':9} {'eps':>4} {'pre-cost':>9} {'cons.net':>9} {'real.net':>9} {'real.2x':>9} {'dd':>8}"
    )
    for period in ("selection", "held_out"):
        for k, v in out[period].items():
            print(
                f"{k:8} {period:9} {v['episodes']:>4} {v['pre_cost_net']:>9,} {v['conservative_net']:>9,} "
                f"{v['realistic_net']:>9,} {v['realistic_net_2x']:>9,} {v['realistic_drawdown']:>8,}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
