"""Run the shadow ledgers for the registered ETF ideas 1 to 3 over the stored daily closes.

Reads daily NIFTYBEES and GOLDBEES closes saved in the Historify database (the nightly capture saves
them), replays every ledger from the registered first signal date, writes a CSV per ledger to
db/etf_ledger/ and prints where each stands. It places no order and changes nothing in Historify.
The rules and numbers are fixed in docs/algos/idea-registration.md; the accounting is in
services/algos/etf_ledger.py.

The exposure-matched benchmarks use weights frozen from a replay on the 15-year history in
db/etf_history/ (write it with scripts/algo_backtest/fetch_etf.py). They are written once to
db/etf_ledger/matched_weights.json and never recomputed from forward results.

Usage:
    uv run python scripts/algo_backtest/run_etf_ledgers.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import etf_ledger as el  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "db" / "etf_ledger"
HISTORY = ROOT / "db" / "etf_history"
FIRST_SIGNAL_DATE = "2026-10-30"
REPLAY_WARMUP_SESSIONS = 300


def stored_closes() -> pd.DataFrame:
    from database import historify_db as db
    from services.algos.forward_shadow_data import to_ist_frame

    columns = {}
    for symbol in (el.NIFTY, el.GOLD):
        frame = to_ist_frame(db.get_ohlcv(symbol, "NSE", "D"))
        if frame.empty:
            return pd.DataFrame()
        frame.index = frame.index.normalize()
        columns[symbol] = frame["close"]
    return pd.DataFrame(columns).sort_index()


def frozen_weights() -> dict[str, dict[str, float]] | None:
    path = OUT / "matched_weights.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    files = [HISTORY / "niftybees.csv", HISTORY / "goldbees.csv"]
    if not all(f.exists() for f in files):
        return None
    history = pd.DataFrame(
        {
            name: pd.read_csv(f, index_col=0, parse_dates=True)["Close"]
            for name, f in zip((el.NIFTY, el.GOLD), files, strict=True)
        }
    ).dropna()
    start = str(history.index[REPLAY_WARMUP_SESSIONS].date())
    weights = {
        idea: el.average_weights(el.run_ledger(idea, history, start).rows)
        for idea in el.all_rules()
    }
    weights["window"] = f"{start} to {history.index[-1].date()}"
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(weights, indent=2), encoding="utf-8")
    return weights


def main() -> int:
    closes = stored_closes()
    if closes.empty:
        print("No stored ETF closes yet. Run capture_option_candles.py after a trading day first.")
        return 1
    try:
        closes = el.validate(closes)
    except el.Blocked as why:
        print(f"Blocked: {why}. Nothing was run; fix or re-capture the closes and run again.")
        return 2
    weights = frozen_weights()
    matched = (
        {k: v for k, v in weights.items() if k in el.all_rules()} if weights is not None else None
    )
    ledgers = el.run_all(closes, FIRST_SIGNAL_DATE, matched)
    OUT.mkdir(parents=True, exist_ok=True)
    for key, ledger in ledgers.items():
        if not ledger.rows.empty:
            ledger.rows.to_csv(OUT / f"{key.replace(':', '_')}.csv", index=False)
    print(
        f"ETF ledgers {el.VERSION} (SHADOW, provisional: splits and distributions are not modelled)"
    )
    print(
        f"  stored closes: {len(closes)} sessions, last {closes.index[-1].date()}; first signal date {FIRST_SIGNAL_DATE}"
    )
    if weights is None:
        print("  exposure-matched holds: not frozen yet (needs db/etf_history from fetch_etf.py)")
    else:
        print(f"  exposure-matched weights frozen on {weights['window']}")
    rows = el.summary({k: v for k, v in ledgers.items() if k.endswith(":base")})
    if all(r.get("sessions", 0) == 0 for r in rows):
        print("  No ledger session yet: the first trade is the close after the first signal date.")
        return 0
    for row in rows:
        if row.get("sessions"):
            print(
                f"  {row['ledger']}: {row['sessions']} sessions, NAV Rs {row['nav']:,.0f} "
                f"({row['return_pct']:+.2f}%), deepest fall Rs {row['drawdown']:,.0f}, "
                f"worst day Rs {row['worst_day']:,.0f}, costs Rs {row['cost']:,.0f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
