"""Search for algos better than the Calm Condor, with the rules fixed in advance.

The grid (52 configurations including the two references):
  condor:   short OTM1-3 x long gap 2-3 (5 shapes) x VIX filter (none, rank >= 50, >= 70)
            x expiry-eve handling (roll to next week, or skip)               = 30
  bull put: same 5 shapes x VIX filter (none, >= 50) x expiry-eve handling   = 20
  references: the catalogue's Calm Condor and Zen                             = 2

Selection uses 2018-2022 only. A candidate is eligible with 150+ train trades, a
train profit factor of at least 1.3, and a profit factor above 1.0 in BOTH halves
of the train period. The top three eligible by train profit factor are judged on
2023 onward, which the selection never saw. "Better than the condor" means, on the
test period: a higher average per trade, a profit factor of at least 1.3, and a
maximum drawdown no worse than 1.5 times the condor's.

Every result is under the conservative model. The full table is printed, so the
selection effect (how many of 52 look good by chance) is visible.

Usage:
    uv run python scripts/algo_backtest/search_candidates.py <data_dir>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_data import load_dir  # noqa: E402
from structures import candidates, plan_fn_for  # noqa: E402

from services.algos.lab import run_lab, summarize  # noqa: E402

TRAIN_END = "2022-12-31"
TRAIN_SPLIT = "2020-12-31"


def sliced(trades, lo=None, hi=None):
    return summarize(
        [t["pnl"] for t in trades if (not lo or t["date"] > lo) and (not hi or t["date"] <= hi)]
    )


def pf(m):
    return m["profit_factor"] if m["profit_factor"] is not None else 99.0


history = load_dir(sys.argv[1])
rows = []
for c in candidates():
    algo, fn = plan_fn_for(c)
    result = run_lab(history, algo, model="conservative", plan_fn=fn)
    tr = result.trades
    rows.append(
        {
            "name": c.name,
            "train": sliced(tr, None, TRAIN_END),
            "h1": sliced(tr, None, TRAIN_SPLIT),
            "h2": sliced(tr, TRAIN_SPLIT, TRAIN_END),
            "test": sliced(tr, TRAIN_END, None),
        }
    )
    print(f"  ran {len(rows):2d}/50 {c.name}", flush=True)

refs = {}
for algo in ("calm_condor", "zen"):
    tr = run_lab(history, algo, model="conservative").trades
    refs[algo] = {"train": sliced(tr, None, TRAIN_END), "test": sliced(tr, TRAIN_END, None)}
base = refs["calm_condor"]["test"]
print(f"\nCONFIGURATIONS TRIED: {len(rows) + len(refs)} (50 grid + 2 references)")
print(
    f"REFERENCE Calm Condor  train PF={pf(refs['calm_condor']['train']):.2f}  test PF={pf(base):.2f} "
    f"avg={base['avg']:.0f} maxDD={base['max_drawdown']:.0f} n={base['trades']}"
)
print(
    f"REFERENCE Zen          train PF={pf(refs['zen']['train']):.2f}  test PF={pf(refs['zen']['test']):.2f} "
    f"avg={refs['zen']['test']['avg']:.0f}"
)

eligible = [
    r
    for r in rows
    if r["train"]["trades"] >= 150
    and pf(r["train"]) >= 1.3
    and pf(r["h1"]) > 1.0
    and pf(r["h2"]) > 1.0
]
eligible.sort(key=lambda r: -pf(r["train"]))
print(f"\nELIGIBLE on train: {len(eligible)} of {len(rows)}")
print("\nTop eligible by TRAIN profit factor, with their TEST result (never seen when chosen):")
print(
    f"  {'candidate':42s} {'trainPF':>7s} {'testPF':>6s} {'n':>4s} {'avg':>5s} {'maxDD':>7s} {'be-cost':>7s}"
)
verdicts = []
for r in eligible[:8]:
    t = r["test"]
    better = (
        t["avg"] > base["avg"] and pf(t) >= 1.3 and t["max_drawdown"] >= 1.5 * base["max_drawdown"]
    )
    mark = "  BETTER" if better else ""
    verdicts.append((r["name"], better))
    print(
        f"  {r['name']:42s} {pf(r['train']):7.2f} {pf(t):6.2f} {t['trades']:4d} {t['avg']:5.0f} "
        f"{t['max_drawdown']:7.0f} {t.get('break_even_cost', 0):7.0f}{mark}"
    )

test_pfs = sorted((pf(r["test"]) for r in rows), reverse=True)
print(
    f"\nSELECTION EFFECT: {sum(p > 1.2 for p in test_pfs)} of {len(rows)} grid configurations have a test PF above 1.2;"
)
print(
    f"  median test PF across the grid = {test_pfs[len(test_pfs) // 2]:.2f}; best = {test_pfs[0]:.2f}"
)
top3 = eligible[:3]
if top3:
    avg_top = sum(pf(r["test"]) for r in top3) / len(top3)
    print(
        f"  mean test PF of the 3 chosen on train = {avg_top:.2f} (train PF of the same three: "
        f"{sum(pf(r['train']) for r in top3) / len(top3):.2f})"
    )
print("\nFULL TABLE (all 50), sorted by train PF:")
for r in sorted(rows, key=lambda r: -pf(r["train"])):
    print(
        f"  {r['name']:42s} train PF={pf(r['train']):5.2f} (n={r['train']['trades']:3d}) "
        f"halves={pf(r['h1']):4.2f}/{pf(r['h2']):4.2f}  test PF={pf(r['test']):5.2f} avg={r['test']['avg']:5.0f}"
    )
