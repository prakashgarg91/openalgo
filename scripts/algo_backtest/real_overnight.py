"""Overnight algos on REAL option prices, next to each pricing model.

For the same days, each algo is priced four ways: the standard model, the
conservative model without the variance clock, the full conservative model, and
actual NSE option prices (the contract's close on the entry day and its open the
next morning). Whichever model tracks the real result is the one to trust.

Costs use the conservative model's itemised costs in every column, so the
columns differ only in how the legs are priced.

Needs the downloads from fetch_history.py and fetch_nse_options.py.

Usage:
    uv run python scripts/algo_backtest/real_overnight.py <history_dir> <nse_days_dir>
"""

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_data import load_dir  # noqa: E402
from structures import SHAPES, Cand, plan_fn_for  # noqa: E402

from services.algos import lab  # noqa: E402

history = load_dir(sys.argv[1])
real = lab.load_real_prices(Path(sys.argv[2]))
first = min(real._days)
last = max(real._days)

ITEMISED = dataclasses.replace(lab.STANDARD, name="itemised_calendar", flat_cost=None)
NO_VAR = dataclasses.replace(
    lab.CONSERVATIVE, name="conservative_no_variance_clock", variance_clock=False
)
for m in (ITEMISED, NO_VAR):
    lab.MODELS[m.name] = m


def line(m):
    if not m["trades"]:
        return "no trades"
    pf = "n/a" if m["profit_factor"] is None else f"{m['profit_factor']:.2f}"
    return (
        f"n={m['trades']:3d} win={m['win_rate']:4.1f}% avg={m['avg']:6.0f} PF={pf:>5s} "
        f"maxDD={m['max_drawdown']:8.0f} gross={m['avg_gross']:6.0f} cost={m['avg_cost']:4.0f}"
    )


print(f"Real option prices: {len(real)} trading days, {first.date()} to {last.date()}\n")
start, end = first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")
for algo in ("calm_condor", "zen", "mirror_zen"):
    print(algo, "(regime-gated, expiry-eve skipped, costs itemised)")
    for label, model, use_real in (
        ("calendar-clock model ", "itemised_calendar", False),
        ("trading-clock model  ", "conservative_no_variance_clock", False),
        ("variance-clock model ", "conservative", False),
        ("REAL option prices   ", "conservative", True),
    ):
        r = lab.run_lab(
            history, algo, model=model, start=start, end=end, real=real if use_real else None
        )
        print(f"  {label} {line(r.metrics)}")
        if use_real:
            print(f"    skipped: {dict(list(r.skipped.items())[:5])}")
            print(
                "    by year:", {y: (v["trades"], round(v["total"])) for y, v in r.yearly.items()}
            )
    print()

print(
    "Condor and bull-put shapes on REAL prices (regime filter as in the catalogue, expiry eve skipped):"
)
for family in ("condor", "bullput"):
    for short, long in SHAPES:
        algo, fn = plan_fn_for(Cand(family, short, long, None, "skip"))
        r = lab.run_lab(
            history, algo, model="conservative", start=start, end=end, real=real, plan_fn=fn
        )
        print(f"  {family:7s} OTM{short}/OTM{long} {line(r.metrics)}")
