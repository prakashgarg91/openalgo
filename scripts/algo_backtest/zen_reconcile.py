"""Reconcile Stratzy Zen's published credit spread trades with our own 5-minute option candles.

For each trade in the exported Zen file, read our 5-minute candles for the same two legs at the
entry and exit moments, and compare Zen's published entry credit, exit debit and result with ours.
Read only: no order is placed and no network is used. Writes ``trades.csv`` and ``summary.txt``
under ``<data_repo>/research/zen_reconcile/``.

Usage:
    uv run python scripts/algo_backtest/zen_reconcile.py <data_repo> [zen_json]
"""

import argparse
import csv
import io
import math
import statistics
import sys
import tarfile
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.algos.zen_trades import IST, ZenTrade, load_trades, parse_symbol  # noqa: E402

DEFAULT_ZEN_JSON = Path(
    "D:/Github/trading-rex-ai/agent-results/022-stratzy/raw/pastAdvices/68596cd26aa2cba24bbb67da.json"
)
OUT_SUBDIR = Path("research") / "zen_reconcile"
STATUSES = (
    "ok",
    "missing_leg_file",
    "no_entry_bar",
    "no_exit_bar",
    "no_exit_time",
    "no_expiry_data",
)
KINDS = ("PE", "CE")
COLUMNS = (
    "advice_id",
    "entry_time",
    "exit_time",
    "kind",
    "expiry",
    "expiry_guess",
    "sold_strike",
    "long_strike",
    "lots",
    "lot_size",
    "zen_credit",
    "our_credit_open",
    "our_credit_close",
    "zen_debit",
    "our_debit_open",
    "our_debit_close",
    "zen_pnl_pts",
    "our_pnl_pts_open",
    "our_pnl_pts_close",
    "zen_pnl_rupees",
    "status",
)
MONTH_NUMBERS = {
    name: number
    for number, name in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"),
        start=1,
    )
}
NO_EXIT_TIME_OF_DAY = time(0, 0)


def floor_to_5(ts: datetime | pd.Timestamp) -> pd.Timestamp:
    """Start of the 5-minute bar containing ``ts``, as naive India wall-clock time.

    Aware input is converted to IST first; naive input is taken as IST already. Our candle
    timestamps are naive IST wall-clock, the same convention as ``OptionBars``.
    """
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert(IST).tz_localize(None)
    return stamp.floor("5min")


def month_expiry_guess(symbol: str, expiries) -> date | None:
    """Latest expiry in the symbol's month and year, for monthly-format symbols.

    ``NIFTY26SEP23000PE`` carries no day, so it is matched to the latest expiry in
    ``expiries`` that falls in September 2026. Weekly symbols carry their own day and
    return None here, as do unparseable symbols and months with no expiry.
    """
    parsed = parse_symbol(symbol)
    if parsed is None or parsed.expiry is not None:
        return None
    month = MONTH_NUMBERS.get(parsed.expiry_code[2:])
    if month is None:
        return None
    year = 2000 + int(parsed.expiry_code[:2])
    matches = [e for e in expiries if e.year == year and e.month == month]
    return max(matches) if matches else None


def _finite(value) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _bar_at(frame: pd.DataFrame, ts: pd.Timestamp):
    """The bar starting at ``ts`` with a finite open and close, else None."""
    if ts not in frame.index:
        return None
    bar = frame.loc[ts]
    if not (_finite(bar["open"]) and _finite(bar["close"])):
        return None
    return bar


def pair_bars(sold_frame: pd.DataFrame | None, long_frame: pd.DataFrame | None, ts: pd.Timestamp):
    """The sold and long bars starting at ``ts``. Either is None when it cannot be used."""
    if sold_frame is None or long_frame is None:
        return None, None
    return _bar_at(sold_frame, ts), _bar_at(long_frame, ts)


def spread_points(sold_bar, long_bar, field: str) -> float | None:
    """Sold price minus long price for ``field`` (open or close). None if either bar is missing."""
    if sold_bar is None or long_bar is None:
        return None
    return float(sold_bar[field]) - float(long_bar[field])


def _pairs(rows: list[dict], zen_key: str, ours_key: str) -> list[tuple[float, float]]:
    return [
        (float(row[zen_key]), float(row[ours_key]))
        for row in rows
        if row["status"] == "ok" and row[zen_key] is not None and row[ours_key] is not None
    ]


def _share_within(values: list[float], limit: float) -> float | None:
    if not values:
        return None
    return sum(1 for v in values if v <= limit) / len(values)


def _diff_stats(pairs: list[tuple[float, float]]) -> dict:
    """Ours minus Zen, signed and absolute, for the pairs given."""
    diffs = [ours - zen for zen, ours in pairs]
    absolute = [abs(d) for d in diffs]
    if not pairs:
        return {
            "n": 0,
            "median": None,
            "mean": None,
            "abs_median": None,
            "abs_mean": None,
            "within_3": None,
            "within_8": None,
        }
    return {
        "n": len(pairs),
        "median": statistics.median(diffs),
        "mean": statistics.fmean(diffs),
        "abs_median": statistics.median(absolute),
        "abs_mean": statistics.fmean(absolute),
        "within_3": _share_within(absolute, 3.0),
        "within_8": _share_within(absolute, 8.0),
    }


def _correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs = [zen for zen, _ in pairs]
    ys = [ours for _, ours in pairs]
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _pnl_stats(rows: list[dict], zen_key: str, ours_key: str) -> dict:
    pairs = _pairs(rows, zen_key, ours_key)
    return {
        "n": len(pairs),
        "correlation": _correlation(pairs),
        "zen_total": sum(zen for zen, _ in pairs),
        "our_total": sum(ours for _, ours in pairs),
    }


def summarize_rows(rows: list[dict]) -> dict:
    """Pure aggregate over reconciled rows. Only status "ok" rows feed the comparisons."""
    status_counts = dict.fromkeys(STATUSES, 0)
    kind_counts = dict.fromkeys(KINDS, 0)
    ok_kind_counts = dict.fromkeys(KINDS, 0)
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        if row["kind"] in kind_counts:
            kind_counts[row["kind"]] += 1
            if row["status"] == "ok":
                ok_kind_counts[row["kind"]] += 1
    return {
        "trades": len(rows),
        "status_counts": status_counts,
        "kind_counts": kind_counts,
        "ok_kind_counts": ok_kind_counts,
        "entry": _diff_stats(_pairs(rows, "zen_credit", "our_credit_close")),
        "exit": _diff_stats(_pairs(rows, "zen_debit", "our_debit_close")),
        "pnl_open": _pnl_stats(rows, "zen_pnl_pts", "our_pnl_pts_open"),
        "pnl_close": _pnl_stats(rows, "zen_pnl_pts", "our_pnl_pts_close"),
    }


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _pct(value) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def format_summary(summary: dict) -> str:
    lines = [
        f"Trades: {summary['trades']}",
        "By status:",
    ]
    lines += [f"  {status}: {summary['status_counts'][status]}" for status in STATUSES]
    lines.append(
        "By kind (all trades): "
        + ", ".join(f"{kind} {summary['kind_counts'][kind]}" for kind in KINDS)
    )
    lines.append(
        "By kind (status ok): "
        + ", ".join(f"{kind} {summary['ok_kind_counts'][kind]}" for kind in KINDS)
    )
    for label, key in (
        ("Entry credit (ours close minus Zen)", "entry"),
        ("Exit debit (ours close minus Zen)", "exit"),
    ):
        stats = summary[key]
        lines += [
            f"{label}, n={stats['n']}:",
            f"  median signed difference: {_fmt(stats['median'])}",
            f"  mean signed difference: {_fmt(stats['mean'])}",
            f"  median absolute difference: {_fmt(stats['abs_median'])}",
            f"  mean absolute difference: {_fmt(stats['abs_mean'])}",
            f"  within 3 points: {_pct(stats['within_3'])}",
            f"  within 8 points: {_pct(stats['within_8'])}",
        ]
    for label, key, ours_label in (
        ("PnL points, open variant", "pnl_open", "ours (open minus open)"),
        ("PnL points, close variant", "pnl_close", "ours (close minus close)"),
    ):
        stats = summary[key]
        lines += [
            f"{label}, n={stats['n']}:",
            f"  correlation Zen vs ours: {_fmt(stats['correlation'], 3)}",
            f"  total Zen points: {_fmt(stats['zen_total'])}",
            f"  total {ours_label} points: {_fmt(stats['our_total'])}",
        ]
    return "\n".join(lines) + "\n"


def _read_expiry_archive(path: Path) -> dict | None:
    """Every leg in one expiry archive, keyed by (kind, strike). None when the archive is absent.

    Read in memory with tarfile; nothing is extracted to disk.
    """
    if not path.exists():
        return None
    frames: dict[tuple[str, float], pd.DataFrame] = {}
    with tarfile.open(path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            parts = Path(member.name).stem.split("_")
            if len(parts) != 3 or parts[1] not in ("CE", "PE"):
                continue
            try:
                strike = float(parts[2])
            except ValueError:
                continue
            handle = tar.extractfile(member)
            if handle is None:
                continue
            data = handle.read()
            frame = (
                pd.read_csv(io.BytesIO(data), parse_dates=["timestamp"])
                .set_index("timestamp")
                .sort_index()
            )
            frames[(parts[1], strike)] = frame[~frame.index.duplicated(keep="last")]
    return frames


class _ExpiryCache:
    """Holds the legs of one expiry at a time."""

    def __init__(self, data_repo: Path, expiries: set[date]):
        self._repo = data_repo
        self._expiries = expiries
        self._expiry: date | None = None
        self._frames: dict | None = None

    def frames(self, expiry: date) -> dict | None:
        if expiry not in self._expiries:
            return None
        if expiry != self._expiry:
            self._frames = _read_expiry_archive(
                self._repo / "bars5m" / f"{expiry.isoformat()}.tar.gz"
            )
            self._expiry = expiry
        return self._frames


def _manifest_expiries(data_repo: Path) -> list[date]:
    with (data_repo / "MANIFEST.csv").open(encoding="utf-8") as handle:
        found = []
        for row in csv.DictReader(handle):
            try:
                found.append(date.fromisoformat(row["expiry"].strip()))
            except (KeyError, AttributeError, ValueError):
                continue
    return sorted(set(found))


def _resolve_expiry(trade: ZenTrade, expiries: list[date]) -> tuple[date | None, bool]:
    if trade.expiry is not None:
        return trade.expiry, False
    guess = month_expiry_guess(trade.sold_symbol, expiries)
    return guess, guess is not None


def _reconcile_trade(
    trade: ZenTrade, expiry: date | None, guessed: bool, cache: _ExpiryCache
) -> dict:
    row: dict = dict.fromkeys(COLUMNS)
    exit_ist = trade.exit_time.astimezone(IST) if trade.exit_time is not None else None
    row.update(
        advice_id=trade.advice_id,
        entry_time=trade.entry_time.astimezone(IST).isoformat(),
        exit_time=exit_ist.isoformat() if exit_ist is not None else None,
        kind=trade.kind,
        expiry=expiry.isoformat() if expiry is not None else None,
        expiry_guess=guessed if expiry is not None else None,
        sold_strike=trade.sold_strike,
        long_strike=trade.long_strike,
        lots=trade.lots,
        lot_size=trade.lot_size,
        zen_credit=trade.entry_credit,
        zen_debit=trade.exit_debit,
        zen_pnl_pts=(
            trade.entry_credit - trade.exit_debit if trade.exit_debit is not None else None
        ),
        zen_pnl_rupees=trade.pnl,
    )

    legs = cache.frames(expiry) if expiry is not None else None
    if legs is None:
        row["status"] = "no_expiry_data"
        return row
    sold_frame = legs.get((trade.kind, trade.sold_strike))
    long_frame = legs.get((trade.kind, trade.long_strike))
    if sold_frame is None or long_frame is None:
        row["status"] = "missing_leg_file"
        return row

    sold_entry, long_entry = pair_bars(sold_frame, long_frame, floor_to_5(trade.entry_time))
    if sold_entry is None or long_entry is None:
        row["status"] = "no_entry_bar"
        return row
    row["our_credit_open"] = spread_points(sold_entry, long_entry, "open")
    row["our_credit_close"] = spread_points(sold_entry, long_entry, "close")

    if exit_ist is None or exit_ist.time() == NO_EXIT_TIME_OF_DAY:
        row["status"] = "no_exit_time"
        return row
    sold_exit, long_exit = pair_bars(sold_frame, long_frame, floor_to_5(exit_ist))
    if sold_exit is None or long_exit is None:
        row["status"] = "no_exit_bar"
        return row
    row["our_debit_open"] = spread_points(sold_exit, long_exit, "open")
    row["our_debit_close"] = spread_points(sold_exit, long_exit, "close")
    row["our_pnl_pts_open"] = row["our_credit_open"] - row["our_debit_open"]
    row["our_pnl_pts_close"] = row["our_credit_close"] - row["our_debit_close"]
    row["status"] = "ok"
    return row


def reconcile(data_repo: Path, zen_json: Path) -> list[dict]:
    """One row per trade in the exported Zen file, oldest first."""
    return reconcile_trades(data_repo, load_trades(Path(zen_json)))


def reconcile_trades(data_repo: Path, trades: list[ZenTrade]) -> list[dict]:
    """One row per trade, in the order given."""
    data_repo = Path(data_repo)
    expiries = _manifest_expiries(data_repo)
    resolved = [_resolve_expiry(trade, expiries) for trade in trades]
    # Process by expiry so each archive is read once; results keep the original order.
    order = sorted(
        range(len(trades)),
        key=lambda i: (resolved[i][0] is None, resolved[i][0] or date.min, i),
    )
    cache = _ExpiryCache(data_repo, set(expiries))
    results: list[dict | None] = [None] * len(trades)
    for i in order:
        expiry, guessed = resolved[i]
        results[i] = _reconcile_trade(trades[i], expiry, guessed, cache)
    return [row for row in results if row is not None]


def _csv_value(value):
    if isinstance(value, float):
        return round(value, 4)
    return "" if value is None else value


def write_outputs(rows: list[dict], summary: dict, out_dir: Path) -> str:
    """Write trades.csv and summary.txt into ``out_dir``. Returns the summary text."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "trades.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row[key]) for key in COLUMNS})
    text = format_summary(summary)
    (out_dir / "summary.txt").write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile Zen's published trades with our own 5-minute option candles (read only)."
    )
    parser.add_argument("data_repo", type=Path, help="path to the openalgo-data repository")
    parser.add_argument(
        "zen_json",
        nargs="?",
        type=Path,
        default=DEFAULT_ZEN_JSON,
        help="exported Zen advices file",
    )
    args = parser.parse_args(argv)
    rows = reconcile(args.data_repo, args.zen_json)
    summary = summarize_rows(rows)
    text = write_outputs(rows, summary, args.data_repo / OUT_SUBDIR)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
