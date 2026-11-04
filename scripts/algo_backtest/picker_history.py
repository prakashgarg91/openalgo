"""Past weekly results for each structure in the strategy picker (descriptive, not a trial).

Replays every picker structure that the end-of-day engine can price, on the NSE end-of-day files in the private
data repository: entered two sessions before a weekly expiry, held to expiry, after realistic costs, one lot of
that week's real size. Weeks entered above India VIX 20 are skipped by the engine, so there is no history for
them. Writes ``db/picker_history/history.json``, which the picker reads. Read only; places no order.

This is a description of what each structure did, not a selection: it is shown beside the live prices so the
trader can see the spread of outcomes, never to rank by past profit. Nothing here is registered or counted.

Usage:
    uv run python scripts/algo_backtest/picker_history.py <data_repo>
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import eod_screen as es  # noqa: E402
from services.algos import nse_lots, picker  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "db" / "picker_history" / "history.json"
FIRST = pd.Timestamp("2021-04-01")
LAST = pd.Timestamp("2026-10-27")
LOWER_LEVEL = 0.05  # a 95 percent lower bound on the mean, for display; not the register's bar
MAX_LEGS = 4  # the engine's grammar; wider structures are not replayed here


def expand_legs(tpl: picker.Template) -> tuple[es.Leg, ...] | None:
    """The engine's legs for a template, a quantity of two written as two legs. None if not expressible."""
    legs: list[es.Leg] = []
    for leg in tpl.legs:
        legs.extend(
            es.Leg(leg.kind, leg.offset * picker.STRIKE_STEP, 1 if leg.side == "B" else -1)
            for _ in range(leg.qty)
        )
    return tuple(legs) if len(legs) <= MAX_LEGS else None


def undefined_loss(tpl: picker.Template) -> bool:
    """Short calls beyond the long ones: a bad week there is not bounded, so the replay's worst is not a limit."""
    calls = sum((1 if leg.side == "B" else -1) * leg.qty for leg in tpl.legs if leg.kind == "CE")
    return calls < 0


def summarize(nets: list[float], vix_at_entry: list[float], entries: list[pd.Timestamp]) -> dict:
    """Spread of weekly outcomes in rupees, with the older and the most recent third kept apart."""
    values = np.array(nets, dtype=float)
    n = len(values)
    if n == 0:
        return {"replayable": False, "reason": "No week could be priced from the stored data."}
    order = np.argsort(np.array(entries, dtype="datetime64[ns]"))
    chrono = values[order]
    third = max(1, n // 3)
    cells = {}
    for name, lo, hi in picker.VIX_BUCKETS:
        mask = np.array([lo <= v < hi for v in vix_at_entry])
        part = values[mask]
        if len(part):
            cells[name] = {
                "trades": int(len(part)),
                "mean": round(float(part.mean()), 1),
                "win_rate": round(float((part > 0).mean()), 3),
                "worst": round(float(part.min()), 1),
            }
    return {
        "replayable": True,
        "trades": int(n),
        "mean": round(float(values.mean()), 1),
        "median": round(float(np.median(values)), 1),
        "win_rate": round(float((values > 0).mean()), 3),
        "worst": round(float(values.min()), 1),
        "best": round(float(values.max()), 1),
        "p05": round(float(np.quantile(values, 0.05)), 1),
        "mean_lower": round(float(es.bootstrap_lower(values, level=LOWER_LEVEL)), 1),
        "older_mean": round(float(chrono[: n - third].mean()), 1) if n > third else None,
        "recent_mean": round(float(chrono[n - third :].mean()), 1),
        "by_vix": cells,
    }


def load_daily(path: Path) -> pd.Series:
    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index, utc=True)
    close = frame["close"]
    close.index = pd.DatetimeIndex(
        close.index.tz_convert("Asia/Kolkata").tz_localize(None)
    ).normalize()
    return close[~close.index.duplicated(keep="last")]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    repo = Path(sys.argv[1])
    frames = [pd.read_csv(f) for f in sorted((repo / "nse_fo_eod").glob("nifty_fo_*.csv.gz"))]
    chain = es.Chain(pd.concat(frames, ignore_index=True))
    nifty = load_daily(repo / "context" / "daily" / "_NSEI.csv")
    vix = load_daily(repo / "context" / "daily" / "_INDIAVIX.csv")
    out = {
        "generated": str(pd.Timestamp.now().date()),
        "period": [str(FIRST.date()), str(LAST.date())],
        "rule": "entered two sessions before a weekly expiry, held to expiry, after realistic costs, one lot",
        "structures": {},
    }
    for tpl in picker.TEMPLATES:
        legs = expand_legs(tpl)
        if legs is None:
            out["structures"][tpl.id] = {
                "replayable": False,
                "reason": "More legs than the replay engine prices.",
            }
            continue
        spec = es.Spec(tpl.id, "weekly", legs, None)
        result = es.simulate(spec, chain, nifty, vix, nse_lots.nifty_lot, FIRST, LAST)
        nets = [t["net"] for t in result.trades]
        levels = [float(vix.get(t["entry"], np.nan)) for t in result.trades]
        row = summarize(nets, levels, [t["entry"] for t in result.trades])
        if row.get("replayable") and undefined_loss(tpl):
            row["note"] = "Loss is not bounded, so the worst week shown is not a limit."
        out["structures"][tpl.id] = row
        print(f"  {tpl.id}: {row.get('trades', 0)} weeks, mean {row.get('mean')}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
