"""The trader's tracked picks: each structure picked from the Strategy picker is recorded with its fit score and entry prices, followed with live prices, and closed with a result. After enough closed picks the log says whether the fit score meant anything. No order is ever placed from here. File based (one JSON line per pick), no database."""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path

REQUIRED = ("template_id", "name", "fit", "expiry", "legs", "lot")
COPIED = (
    "template_id",
    "name",
    "fit",
    "components",
    "expiry",
    "legs",
    "lot",
    "capital_required",
    "max_loss",
    "conditions",
)
MIN_FOR_VERDICT = 20
MIN_FOR_CORRELATION = 10

_LOCK = threading.Lock()
_LEG_MESSAGE = "Every leg needs a type, strike, side, quantity and entry price."


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_legs(legs: object) -> None:
    if not isinstance(legs, list) or not legs:
        raise ValueError(_LEG_MESSAGE)
    for leg in legs:
        if not isinstance(leg, dict):
            raise ValueError(_LEG_MESSAGE)
        if leg.get("kind") not in ("CE", "PE"):
            raise ValueError(_LEG_MESSAGE)
        if not _is_number(leg.get("strike")):
            raise ValueError(_LEG_MESSAGE)
        if leg.get("side") not in ("B", "S"):
            raise ValueError(_LEG_MESSAGE)
        qty = leg.get("qty")
        if not _is_whole(qty) or qty < 1:
            raise ValueError(_LEG_MESSAGE)
        price = leg.get("price")
        if not _is_number(price) or price <= 0:
            raise ValueError(_LEG_MESSAGE)


def _raw_lines(path: Path) -> list[str]:
    """Return the non-blank lines of the file, exactly as written."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [line.rstrip("\r\n") for line in handle if line.strip()]


def _parse(line: str) -> dict | None:
    """Return the pick on a line, or None when the line is not a JSON object."""
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _write_atomic(path: Path, lines: list[str]) -> None:
    """Replace the whole file in one step so a crash never leaves it half written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("".join(line + "\n" for line in lines))
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class PickLog:
    """Append-only log of tracked picks, one JSON object per line."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def all(self) -> list[dict]:
        """Return every readable pick in file order; unreadable lines are skipped."""
        with _LOCK:
            return self._picks()

    def _picks(self) -> list[dict]:
        picks = []
        for line in _raw_lines(self.path):
            pick = _parse(line)
            if pick is not None:
                picks.append(pick)
        return picks

    def add(self, pick: dict, now: datetime) -> dict:
        """Validate and record a pick as open. Places no order."""
        for key in REQUIRED:
            if key not in pick:
                raise ValueError(f"The pick is missing {key}.")
        _check_legs(pick["legs"])
        fit = pick["fit"]
        if not _is_number(fit) or not 0 <= fit <= 100:
            raise ValueError("The fit score must be a number between 0 and 100.")
        lot = pick["lot"]
        if not _is_whole(lot) or lot < 1:
            raise ValueError("The lot must be a positive whole number.")

        with _LOCK:
            count = len(self._picks())
            record = {key: pick[key] for key in COPIED if key in pick}
            record["id"] = f"{now:%Y%m%d%H%M%S}-{count + 1}"
            record["opened"] = now.isoformat()
            record["status"] = "open"
            record["pnl"] = None
            record["closed"] = None
            self.path.parent.mkdir(parents=True, exist_ok=True)
            needs_break = (
                self.path.exists()
                and self.path.stat().st_size > 0
                and not self._ends_with_newline()
            )
            with self.path.open("a", encoding="utf-8") as handle:
                if needs_break:
                    handle.write("\n")
                handle.write(json.dumps(record, default=str) + "\n")
        return record

    def _ends_with_newline(self) -> bool:
        with self.path.open("rb") as handle:
            handle.seek(-1, os.SEEK_END)
            return handle.read(1) == b"\n"

    def close(self, pick_id: str, pnl: float, now: datetime) -> dict:
        """Record the result of an open pick and return the updated pick."""
        with _LOCK:
            lines = _raw_lines(self.path)
            for index, line in enumerate(lines):
                pick = _parse(line)
                if pick is None or pick.get("id") != pick_id:
                    continue
                if pick.get("status") == "closed":
                    raise ValueError("This pick is already closed.")
                pick["status"] = "closed"
                pick["pnl"] = round(float(pnl), 2)
                pick["closed"] = now.isoformat()
                lines[index] = json.dumps(pick, default=str)
                _write_atomic(self.path, lines)
                return pick
        raise ValueError("No such pick.")

    @staticmethod
    def mark(pick: dict, mids: dict[tuple[str, float], float]) -> float | None:
        """Return the unrealized rupees at the given mid prices, or None if a leg has no price."""
        total = 0.0
        for leg in pick["legs"]:
            key = (leg["kind"], float(leg["strike"]))
            if key not in mids:
                return None
            sign = 1 if leg["side"] == "B" else -1
            total += sign * leg["qty"] * (mids[key] - leg["price"])
        return round(pick["lot"] * total, 0)


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        average = (start + end) / 2 + 1
        for position in range(start, end + 1):
            ranks[order[position]] = average
        start = end + 1
    return ranks


def rank_correlation(xs: list[float], ys: list[float]) -> float | None:
    """Rank-order correlation of the two lists, with average ranks for ties; None when it is undefined."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    if len(set(xs)) == 1 or len(set(ys)) == 1:
        return None
    rx = _average_ranks(xs)
    ry = _average_ranks(ys)
    n = len(rx)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n
    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry, strict=True))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)
    if var_x == 0 or var_y == 0:
        return None
    return covariance / math.sqrt(var_x * var_y)


def summarize(picks: list[dict]) -> dict:
    """Statistics over closed picks; open picks are counted but not measured."""
    open_count = sum(1 for pick in picks if pick.get("status") == "open")
    closed = [
        pick for pick in picks if pick.get("status") == "closed" and pick.get("pnl") is not None
    ]
    n = len(closed)
    pnls = [float(pick["pnl"]) for pick in closed]
    wins = sum(1 for value in pnls if value > 0)

    win_rate = round(wins / n, 3) if n else None
    average_pnl = round(sum(pnls) / n, 2) if n else None
    worst = round(min(pnls), 2) if n else None
    best = round(max(pnls), 2) if n else None
    total = round(sum(pnls), 2)

    correlation = None
    if n >= MIN_FOR_CORRELATION:
        raw = rank_correlation([float(pick["fit"]) for pick in closed], pnls)
        correlation = None if raw is None else round(raw, 2)

    if n < MIN_FOR_VERDICT:
        verdict = f"Too few closed picks ({n} of {MIN_FOR_VERDICT}) to say whether the fit score means anything."
    elif correlation is not None and correlation > 0.3:
        verdict = "Higher fit scores tended to do better."
    elif correlation is not None and correlation < -0.3:
        verdict = "Higher fit scores tended to do worse."
    else:
        verdict = "No clear link between the fit score and the result."

    return {
        "open": open_count,
        "closed": n,
        "wins": wins,
        "win_rate": win_rate,
        "average_pnl": average_pnl,
        "worst": worst,
        "best": best,
        "total": total,
        "correlation": correlation,
        "verdict": verdict,
    }
