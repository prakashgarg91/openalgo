"""Search the non-option algo families on ETF history, judged against cash and buy and hold.

Pre-registered in services/algos/universe.py (grid, split, verdict rules); nothing was tuned after seeing results.

Usage: uv run python scripts/algo_backtest/universe_search.py <etf_dir>
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import mandate, universe  # noqa: E402


def load(directory: Path) -> dict[str, pd.DataFrame]:
    def read(name):
        df = pd.read_csv(directory / f"{name}.csv", index_col=0, parse_dates=True)
        df.index = df.index.tz_localize(None) if df.index.tz else df.index
        return universe.clean(df)

    equity, gold = read("niftybees"), read("goldbees")
    common = equity.index.intersection(gold.index)
    return {"equity": equity.loc[common], "gold": gold.loc[common]}


def line(label, s):
    return (
        f"{label:44s} days={s['days']:4d} total={s['total']:9.0f} CAGR={s['cagr']:6.2f}% "
        f"deepest fall={s['max_drawdown']:9.0f} worst day={s['worst_day']:8.0f}"
    )


def main() -> None:
    bars = load(Path(sys.argv[1]))
    found = universe.search(bars)
    seg = found["segments"]
    print(
        f"Days {bars['equity'].index[0].date()} to {bars['equity'].index[-1].date()}; trials {found['trials']}"
    )
    print("Segments:", seg)
    print(
        f"Rules that earned less than cash on the untouched period: {found['lost_to_cash_on_test']} of {found['trials']}\n"
    )
    for name in ("train", "validate", "test"):
        print(f"-- {name} --")
        print(line("  cash (6%)", found["baselines"]["cash"][name]))
        print(line("  buy and hold Nifty ETF", found["baselines"]["buy_and_hold"][name]))
    print(
        "\nEVERY rule, untouched period (informational; the winner was picked without it), best train score first:"
    )
    for r in sorted(found["rows"], key=lambda r: -r["train_score"]):
        t, v, tr = r["stats"]["test"], r["stats"]["validate"], r["stats"]["train"]
        print(
            f"  {r['strategy'].name:52s} train CAGR={tr['cagr']:6.2f}% validate={v['cagr']:6.2f}% "
            f"test={t['cagr']:6.2f}% (vs cash {r['excess']['test']:8.0f}) test deepest fall={t['max_drawdown']:8.0f}"
        )
    w = found["winner"]
    print("\nWINNER (train, then validate):", w["strategy"].name)
    for name in ("train", "validate", "test"):
        print(line(f"  {name}", w["stats"][name]))
    v = found["verdict"]
    print("VERDICT:", v["headline"])
    for k in (
        "beats_cash",
        "beats_buy_and_hold",
        "lowers_risk_like_buy_and_hold",
        "within_daily_cap",
    ):
        print(f"  {k}: {v[k]}")
    for r in v["reasons"]:
        print("  -", r)

    lo, hi = seg["test"]
    for label, days in (
        ("winner", found["winner_days"]),
        ("buy and hold", found["buy_and_hold_days"]),
    ):
        window = [d for d in days if lo <= d["date"] <= hi]
        sim = mandate.simulate(window, mandate.ONE_LAKH, 1)
        print(
            f"Rs 1,00,000 on the untouched period, {label:13s}: ended {sim['final_equity']:9.0f} ({sim['return_pct']:+.1f}%) "
            f"worst day {sim['worst_day']:8.0f} deepest fall {sim['max_drawdown']:8.0f} within Rs 20,000 cap={sim['within_daily_cap']}"
        )


if __name__ == "__main__":
    main()
