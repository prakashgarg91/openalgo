"""Replay a fixed Zen-shaped credit spread on every month of our own option candles (read only, no order).

Rules, written before any result was read (6 Nov 2026 registration note in
docs/algos/zen-structure-replay-2026-11.md):
  - every session D, nearest weekly expiry E with at least one session after D and at most 6 days away;
  - sold leg at the money (spot at 10:15 rounded to 50), bought leg 400 points away: put spread below,
    call spread above, tested separately (two sides);
  - entry at the open of the 10:15 five-minute bar; exit when the spread costs 31 percent of the credit or
    less (target, 69 percent captured), or at 250 percent of the credit or more (stop, loss 1.5 times the
    credit), checked on bar closes, else at the close of the 15:00 bar on the next session (or the last bar
    on the expiry day);
  - one lot (that expiry's real lot), costs from eod_screen.leg_cost (realistic) and doubled;
  - variant "gate": skip when the previous session's India VIX close is 20 or higher.
Usage: uv run python scripts/algo_backtest/zen_structure_replay.py <data_repo>
"""

import csv
import io
import json
import sys
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import eod_screen as es  # noqa: E402
from services.algos import nse_lots  # noqa: E402

WIDTH, TARGET, STOP = 400, 0.31, 2.5
ZEN_START = pd.Timestamp("2025-07-09")


def load_expiry(repo: Path, expiry: str) -> dict:
    out = {}
    with tarfile.open(repo / "bars5m" / f"{expiry}.tar.gz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            _, kind, strike = Path(m.name).stem.split("_")
            df = pd.read_csv(io.BytesIO(tar.extractfile(m).read()), parse_dates=["timestamp"]).set_index("timestamp")
            out[(kind, int(float(strike)))] = df["close"]
    return out


def daily(repo: Path, name: str) -> pd.Series:
    f = pd.read_csv(repo / "context" / "daily" / name, index_col=0)
    f.index = pd.to_datetime(f.index, utc=True).tz_convert("Asia/Kolkata").tz_localize(None).normalize()
    return f["close"][~f.index.duplicated(keep="last")]


def run(repo: Path) -> pd.DataFrame:
    expiries = sorted(pd.Timestamp(r["expiry"]) for r in csv.DictReader((repo / "MANIFEST.csv").open()))
    idx = pd.read_csv(repo / "index" / "nifty_1m.csv", parse_dates=["timestamp"]).set_index("timestamp").sort_index()["close"]
    vix = daily(repo, "_INDIAVIX.csv")
    sessions = sorted(set(idx.index.normalize()))
    rows = []
    for e in expiries:
        data = load_expiry(repo, e.strftime("%Y-%m-%d"))
        lot = nse_lots.nifty_lot(e)
        if lot is None:
            continue
        for d in sessions:
            if not (0 < (e - d).days <= 6):
                continue
            nxt = [s for s in sessions if s > d]
            if not nxt:
                continue
            d1 = nxt[0]
            if d1 > e:
                continue
            t0 = d + pd.Timedelta(hours=10, minutes=15)
            if t0 not in idx.index:
                continue
            spot = idx.get(t0)
            atm = int(round(spot / 50) * 50)
            prev = [s for s in sessions if s < d]
            vprev = vix.get(prev[-1]) if prev else np.nan
            for side, kind, other in (("PE", "PE", atm - WIDTH), ("CE", "CE", atm + WIDTH)):
                sold, long_ = data.get((kind, atm)), data.get((kind, other))
                if sold is None or long_ is None or t0 not in sold.index or t0 not in long_.index:
                    continue
                spread = (sold - long_).dropna()
                credit = float(spread.loc[t0])
                if credit <= 5:
                    continue
                end = d1 + pd.Timedelta(hours=15)
                path = spread.loc[t0:end]
                path = path.iloc[1:]
                if path.empty:
                    continue
                exit_v, why = float(path.iloc[-1]), "time"
                for ts, v in path.items():
                    if v <= TARGET * credit:
                        exit_v, why = float(v), "target"
                        break
                    if v >= STOP * credit:
                        exit_v, why = float(v), "stop"
                        break
                pts = credit - exit_v
                so, lo = float(sold.loc[t0]), float(long_.loc[t0])
                sx = float(sold.reindex(path.index).ffill().loc[ts if why != "time" else path.index[-1]])
                lx = float(long_.reindex(path.index).ffill().loc[ts if why != "time" else path.index[-1]])
                cost = es.leg_cost(-1, so, sx, d, d1, lot) + es.leg_cost(1, lo, lx, d, d1, lot)
                rows.append({"date": d, "side": side, "expiry": e, "credit": credit, "exit": exit_v, "why": why,
                             "gross": pts * lot, "cost": cost, "net": pts * lot - cost, "net2x": pts * lot - 2 * cost,
                             "vix_prev": vprev})
    return pd.DataFrame(rows)


def stats(g: pd.DataFrame) -> dict:
    if g.empty:
        return {"n": 0}
    g = g.sort_values("date")
    eq = g.net.cumsum()
    day = g.groupby("date").net.sum()
    return {"n": len(g), "net": round(g.net.sum()), "net2x": round(g.net2x.sum()), "win": round((g.net > 0).mean(), 2),
            "mean": round(g.net.mean()), "dd": round(-(eq - eq.cummax()).min()), "worst_day": round(day.min()),
            "stops": int((g.why == "stop").sum()), "targets": int((g.why == "target").sum())}


def main() -> int:
    repo = Path(sys.argv[1])
    df = run(repo)
    out = repo / "research" / "zen_structure_replay"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "trades.csv", index=False)
    result = {}
    for gate in ("no_gate", "vix_gate"):
        d = df if gate == "no_gate" else df[~(df.vix_prev >= 20)]
        for side in ("PE", "CE", "both"):
            s = d if side == "both" else d[d.side == side]
            for per, part in (("before_zen_window", s[s.date < ZEN_START]), ("zen_window", s[s.date >= ZEN_START]), ("all", s)):
                result[f"{gate}/{side}/{per}"] = stats(part)
    (out / "summary.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    for k, v in result.items():
        print(k, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
