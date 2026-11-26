"""Weekly ATM straddle premium at 10:15 against the move that followed (read only, no orders).

For every trading day whose nearest expiry is 1 to 6 calendar days ahead (the window of
services/algos/atm200_rule.py): the straddle is the ATM call close plus the ATM put close on
the 10:15 five-minute bar of that day (spot from the Nifty 1-minute close at 10:15, ATM strike
by atm200_rule.atm_strike), and the move is the absolute Nifty close change from that spot to
the 15:29 one-minute close on the expiry day. A day with any missing value is skipped and
counted. Reported: days, share of days straddle > move, mean and median of straddle/move,
mean straddle and mean move, split by the previous session's India VIX below or at/above its
trailing 60-session median (median of the closes present in those sessions), and by 1-2, 3-4,
5-6 calendar days to expiry.

Usage: python -m scripts.algo_backtest.weekly_premium_vs_move [data_repo]
"""

import csv
import io
import sys
import tarfile
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos import atm200_rule  # noqa: E402

DATA_REPO = Path("D:/Github/openalgo-data")
VIX_WINDOW = 60  # trailing sessions in the VIX median
DTE_BUCKETS = ((1, 2), (3, 4), (5, 6))
BUCKET_ORDER = (
    ("all", "all"),
    ("vix_below", "vix below med60"),
    ("vix_at_above", "vix at/above med60"),
    ("dte_1-2", "dte 1-2"),
    ("dte_3-4", "dte 3-4"),
    ("dte_5-6", "dte 5-6"),
)


def load_expiry(repo: Path, expiry: str) -> dict:
    out = {}
    with tarfile.open(repo / "bars5m" / f"{expiry}.tar.gz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            _, kind, strike = Path(m.name).stem.split("_")
            df = pd.read_csv(
                io.BytesIO(tar.extractfile(m).read()), parse_dates=["timestamp"]
            ).set_index("timestamp")
            out[(kind, int(float(strike)))] = df["close"]
    return out


def daily(repo: Path, name: str) -> pd.Series:
    f = pd.read_csv(repo / "context" / "daily" / name, index_col=0)
    f.index = (
        pd.to_datetime(f.index, utc=True).tz_convert("Asia/Kolkata").tz_localize(None).normalize()
    )
    return f["close"][~f.index.duplicated(keep="last")]


def _dte_bucket(dte: int) -> str:
    for lo, hi in DTE_BUCKETS:
        if lo <= dte <= hi:
            return f"{lo}-{hi}"
    return "other"


def collect(repo: Path, vix_window: int = VIX_WINDOW):
    """One row per session whose nearest expiry is 1-6 calendar days ahead, plus skip counts."""
    expiries = sorted(
        pd.Timestamp(r["expiry"]) for r in csv.DictReader((repo / "MANIFEST.csv").open())
    )
    idx = (
        pd.read_csv(repo / "index" / "nifty_1m.csv", parse_dates=["timestamp"])
        .set_index("timestamp")
        .sort_index()["close"]
    )
    idx = idx[~idx.index.duplicated(keep="last")]
    vix = daily(repo, "_INDIAVIX.csv")
    sessions = sorted(set(idx.index.normalize()))
    vix_s = vix.reindex(pd.DatetimeIndex(sessions))
    rows, skips = [], Counter()
    data, cur_expiry = {}, None
    for i, d in enumerate(sessions):
        e = next((x for x in expiries if 0 < (x - d).days <= 6), None)
        if e is None:
            continue
        t0 = d + pd.Timedelta(hours=10, minutes=15)
        spot = idx.get(t0)
        if pd.isna(spot):
            skips["nifty 10:15 spot missing"] += 1
            continue
        close_e = idx.get(e + pd.Timedelta(hours=15, minutes=29))
        if pd.isna(close_e):
            skips["nifty 15:29 close on expiry day missing"] += 1
            continue
        if e != cur_expiry:
            key = e.strftime("%Y-%m-%d")
            data = load_expiry(repo, key) if (repo / "bars5m" / f"{key}.tar.gz").exists() else None
            cur_expiry = e
        if data is None:
            skips["expiry bars file missing"] += 1
            continue
        atm = atm200_rule.atm_strike(float(spot))
        ce, pe = data.get(("CE", atm)), data.get(("PE", atm))
        if ce is None or pe is None or t0 not in ce.index or t0 not in pe.index:
            skips["atm straddle bar missing"] += 1
            continue
        straddle = float(ce.loc[t0]) + float(pe.loc[t0])
        move = abs(float(close_e) - float(spot))
        if pd.isna(straddle) or move == 0:
            skips[
                "atm straddle bar missing" if pd.isna(straddle) else "zero move (ratio undefined)"
            ] += 1
            continue
        vix_prev = vix_s.iloc[i - 1] if i > 0 else float("nan")
        bucket = None
        if i >= vix_window and not pd.isna(vix_prev):
            # Median over the closes present in the trailing 60 sessions: the VIX file misses
            # a handful of sessions (about four in two years), and dropping every window that
            # touches a gap would leave a third of the days without a bucket.
            window = vix_s.iloc[i - vix_window : i].dropna()
            if len(window):
                med = float(window.median())
                bucket = "below" if vix_prev < med else "at_above"
        dte = (e - d).days
        rows.append(
            {
                "date": d,
                "expiry": e,
                "dte": dte,
                "dte_bucket": _dte_bucket(dte),
                "straddle": straddle,
                "move": move,
                "ratio": straddle / move,
                "vix_prev": None if pd.isna(vix_prev) else float(vix_prev),
                "vix_bucket": bucket,
            }
        )
    return pd.DataFrame(rows), dict(skips)


def stats(g: pd.DataFrame) -> dict:
    if g.empty:
        return {
            "days": 0,
            "share_straddle_gt_move": None,
            "mean_ratio": None,
            "median_ratio": None,
            "mean_straddle": None,
            "mean_move": None,
        }
    return {
        "days": len(g),
        "share_straddle_gt_move": round(float((g.straddle > g.move).mean()), 2),
        "mean_ratio": round(float(g.ratio.mean()), 2),
        "median_ratio": round(float(g.ratio.median()), 2),
        "mean_straddle": round(float(g.straddle.mean()), 1),
        "mean_move": round(float(g.move.mean()), 1),
    }


def summarize(df: pd.DataFrame, skips: dict) -> dict:
    out = {"all": stats(df), "skips": skips, "skipped_days": sum(skips.values())}
    for b in ("below", "at_above"):
        out[f"vix_{b}"] = stats(df[df.vix_bucket == b])
    for lo, hi in DTE_BUCKETS:
        out[f"dte_{lo}-{hi}"] = stats(df[df.dte_bucket == f"{lo}-{hi}"])
    out["vix_bucket_missing_days"] = int(df.vix_bucket.isna().sum()) if len(df) else 0
    return out


def _cell(v, width: int) -> str:
    if v is None:
        return " " * (width - 1) + "-"
    return f"{v:{width}.2f}"


def render(summary: dict, repo: Path) -> str:
    lines = [
        f"weekly ATM straddle premium at 10:15 vs the move to the expiry 15:29 close (points, repo {repo})",
        f"{'bucket':<20}{'days':>6}  {'share s>m':>9}  {'mean s/m':>8}  {'med s/m':>7}  {'mean strad':>10}  {'mean move':>9}",
    ]
    for key, label in BUCKET_ORDER:
        s = summary[key]
        lines.append(
            f"{label:<20}{s['days']:>6}  {_cell(s['share_straddle_gt_move'], 9):>9}"
            f"  {_cell(s['mean_ratio'], 8):>8}  {_cell(s['median_ratio'], 7):>7}"
            f"  {_cell(s['mean_straddle'], 10):>10}  {_cell(s['mean_move'], 9):>9}"
        )
    skips = ", ".join(f"{k}: {v}" for k, v in sorted(summary["skips"].items())) or "none"
    lines.append(f"skipped days: {summary['skipped_days']} ({skips})")
    if summary["vix_bucket_missing_days"]:
        lines.append(
            f"days counted overall but without a VIX bucket: {summary['vix_bucket_missing_days']}"
        )
    return "\n".join(lines)


def main() -> int:
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_REPO
    df, skips = collect(repo)
    print(render(summarize(df, skips), repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
