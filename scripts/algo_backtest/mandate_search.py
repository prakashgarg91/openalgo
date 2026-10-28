"""Find the best algo for a Rs 1,00,000 account that may lose at most Rs 20,000 a day, on REAL option prices.

Pre-registered before any result was seen (nothing below was changed after running):

Account    capital 1,00,000, daily loss cap 20,000, one position a day. A spread loses at most its
           width, so only widths up to 150 points qualify (1 lot x 75 x 150 = 11,250 under the cap).
Data       NSE option prices 2022-01 to 2026-10 (entry at the contract's close, exit at its open
           `hold` trading days later), daily index, VIX, US, crude and dollar history for the regime.
Costs      the Lab's conservative itemised costs, applied to every candidate and to Zen.
Studies    bullish lean:  bull put (credit) and bull call (debit) spreads
           bearish lean:  bear call (credit) and bear put (debit) spreads
           neutral lean:  iron condors
           each over 5 strike shapes, calm or calm+trending days, and holds of 1, 2 and 3 days.
Rule       the Builder's walk-forward: choose on the first half of the trades, narrow on the next
           quarter, read ONLY the winner on the last quarter. Edge is shown only if the winner has a
           profit factor of at least 1.2 on validation and 1.35 on the untouched period, with at
           least 40 trades in each (lowered from 60 because one lean is a subset of the days).
Baseline   the catalogue's Zen (bullish study: its bull put days), Calm Condor (neutral study).

Usage:
    uv run python scripts/algo_backtest/mandate_search.py <history_dir> <real_options_dir> <study> [out.json]
    study: bullish | bearish | neutral
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_data import load_dir  # noqa: E402

from services.algos import builder, lab, mandate  # noqa: E402
from services.algos.templates import (  # noqa: E402
    Plan,
    condor_config,
    debit_spread_config,
    spread_config,
)

ACCOUNT = mandate.ONE_LAKH
builder.MIN_EVAL_TRADES = 40  # pre-registered: one lean is a subset of the days

SHAPES_CREDIT = [(1, 3), (1, 4), (2, 4), (2, 5), (3, 5)]
SHAPES_DEBIT = [(0, 1), (0, 2), (0, 3), (1, 3), (1, 4)]
LABEL_SETS = [("calm",), ("calm", "trending")]
HOLDS = (1, 2, 3)
STUDIES = {
    "bullish": ("bullish", ["bull_put", "bull_call"], "zen", "bull_put"),
    "bearish": ("bearish", ["bear_call", "bear_put"], "zen", "bear_call"),
    "neutral": ("neutral", ["condor"], "calm_condor", None),
}


@dataclass(frozen=True)
class Candidate:
    family: str
    short: int
    long: int
    labels: tuple[str, ...]
    hold: int
    bias: str

    @property
    def name(self) -> str:
        return (
            f"{self.family} OTM{self.short}/OTM{self.long} {'+'.join(self.labels)} "
            f"hold {self.hold}d"
        )

    def to_dict(self) -> dict:
        return {**self.__dict__, "labels": list(self.labels)}

    @property
    def width(self) -> int:
        return (self.long - self.short) * 50


def plan_fn_for(c: Candidate):
    def plan_fn(regime, inputs, dte, extra):
        skip = Plan("calm_condor", "skip", "", None, 0, None, None)
        if regime.label not in c.labels or regime.confidence < 0.5 or regime.bias != c.bias:
            return skip
        if dte <= c.hold:
            return skip
        short, long = f"OTM{c.short}", f"OTM{c.long}"
        if c.family == "condor":
            cfg = condor_config("c", 1, "weekly", short_offset=short, long_offset=long)
            return Plan("calm_condor", "trade", "", cfg, 1, 0.0, "iron_condor")
        if c.family in ("bull_call", "bear_put"):
            cfg = debit_spread_config(
                "c", c.family, 1, "weekly", near_offset=short, far_offset=long
            )
        else:
            cfg = spread_config("c", c.family, 1, "weekly", short_offset=short, long_offset=long)
        return Plan("calm_condor", "trade", "", cfg, 1, 0.0, c.family)

    return plan_fn


def candidates(bias: str, families: list[str]) -> list[Candidate]:
    out = []
    for family in families:
        shapes = SHAPES_DEBIT if family in ("bull_call", "bear_put") else SHAPES_CREDIT
        for short, long in shapes:
            for labels in LABEL_SETS:
                for hold in HOLDS:
                    c = Candidate(family, short, long, labels, hold, bias)
                    # 1 lot must fit under the daily cap; a condor risks one wing.
                    if ACCOUNT.lots(c.width, lab.LOT_SIZE) >= 1:
                        out.append(c)
    return out


def main() -> None:
    history_dir, real_dir, study = sys.argv[1], sys.argv[2], sys.argv[3]
    out_path = sys.argv[4] if len(sys.argv) > 4 else None
    bias, families, base_algo, base_side = STUDIES[study]
    history = load_dir(history_dir)
    real = lab.load_real_prices(Path(real_dir))
    cands = candidates(bias, families)
    cache: dict[Candidate, list] = {}

    def run(c: Candidate):
        res = lab.run_lab(
            history,
            "calm_condor",
            model="conservative",
            plan_fn=plan_fn_for(c),
            real=real,
            hold=c.hold,
        )
        cache[c] = res.trades
        return res.trades

    def baseline():
        trades = lab.run_lab(history, base_algo, model="conservative", real=real).trades
        return [t for t in trades if base_side is None or t["side"] == base_side]

    print(f"Study {study}: {len(cands)} candidates on {len(real)} real option days", flush=True)
    found = builder.search(cands, run, baseline=baseline)
    seg = {k: tuple(v) for k, v in found["segments"].items()}
    base_trades = baseline()

    def cut(trades, name):
        lo, hi = seg[name]
        return [
            t
            for t in trades
            if (t["date"] >= lo if name == "train" else t["date"] > lo) and t["date"] <= hi
        ]

    def row(trades):
        return lab.summarize([t["pnl"] for t in trades])

    def line(label, trades):
        parts = []
        for name in ("train", "validate", "test"):
            m = row(cut(trades, name))
            pf = m["profit_factor"]
            parts.append(
                f"{name}: n={m['trades']:3d} avg={m['avg']:7.0f} tot={m['total']:8.0f} PF={'inf' if pf is None and m['total'] > 0 else pf}"
            )
        return f"  {label:46s} " + " | ".join(parts)

    print(f"\nSegments: {seg}")
    print(
        f"TRIALS: {found['trials']}   lost money on the untouched period: {found['lost_on_test']}"
    )
    print(line(f"BASELINE {base_algo} ({base_side or 'all'})", base_trades))
    print(
        "\nEVERY candidate (informational; the winner was chosen WITHOUT looking at the test column):"
    )
    for c in sorted(cands, key=lambda c: -(builder.score(cut(cache[c], "train")) or -1e18)):
        print(line(c.name, cache[c]))
    w = found["winner"]
    print("\nWINNER (chosen on train, narrowed on validate):", w["name"] if w else None)
    print("VERDICT:", found["verdict"]["headline"])
    for r in found["verdict"]["reasons"]:
        print("  -", r)

    sims = {}
    if w:
        wc = next(c for c in cands if c.to_dict() == w["spec"])
        sims["winner"] = mandate.simulate(cut(cache[wc], "test"), ACCOUNT, 1)
    sims["baseline"] = mandate.simulate(cut(base_trades, "test"), ACCOUNT, 1)
    print("\nRs 1,00,000 account, one lot, on the untouched period:")
    for k, s in sims.items():
        print(
            f"  {k:9s} trades={s['days_traded']:3d} final={s['final_equity']:9.0f} ({s['return_pct']:+.1f}%) "
            f"worst day={s['worst_day']:8.0f} max drawdown={s['max_drawdown']:8.0f} within Rs 20,000 cap={s['within_daily_cap']}"
        )
    if out_path:
        Path(out_path).write_text(
            json.dumps(
                {
                    "study": study,
                    "found": {k: v for k, v in found.items() if k != "caveats"},
                    "sims": {
                        k: {kk: vv for kk, vv in s.items() if kk != "curve"}
                        for k, s in sims.items()
                    },
                },
                default=str,
            )
        )


if __name__ == "__main__":
    main()
