"""Days the trader tells the algos to sit out: the budget, a central-bank decision, big results.

OpenAlgo has no reliable free source for a calendar of scheduled events, so the trader keeps
this short list. An entry blocks the day itself and the last trading day before it, because an
overnight position opened the evening before would carry straight into the event.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from services.algos.context import RegimeResult

PATH = Path(__file__).resolve().parents[2] / "db" / "algo_events.json"
MAX_ENTRIES = 100
MAX_LABEL = 60
HORIZON_DAYS = 400


class EventError(ValueError):
    """A trader-facing reason an entry was refused."""


def load(path: Path | None = None) -> list[dict[str, str]]:
    path = path or PATH
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    return sorted(
        (e for e in data if isinstance(e, dict) and "date" in e and "label" in e),
        key=lambda e: e["date"],
    )


def _save(entries: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries))
    tmp.replace(path)


def add(
    raw_date: Any, raw_label: Any, today: date, path: Path | None = None
) -> list[dict[str, str]]:
    path = path or PATH
    try:
        day = date.fromisoformat(str(raw_date))
    except ValueError:
        raise EventError("Enter the day like 2026-02-01.") from None
    if not (today <= day <= today + timedelta(days=HORIZON_DAYS)):
        raise EventError("Pick a day from today to about a year ahead.")
    label = str(raw_label or "").strip()
    if not label or len(label) > MAX_LABEL:
        raise EventError(
            f"Give it a short name of up to {MAX_LABEL} characters, like Union Budget."
        )
    entries = [e for e in load(path) if e["date"] != day.isoformat()]
    if len(entries) >= MAX_ENTRIES:
        raise EventError(f"You can list {MAX_ENTRIES} days. Remove one first.")
    entries.append({"date": day.isoformat(), "label": label})
    entries.sort(key=lambda e: e["date"])
    _save(entries, path)
    return entries


def remove(raw_date: str, path: Path | None = None) -> list[dict[str, str]]:
    path = path or PATH
    entries = [e for e in load(path) if e["date"] != raw_date]
    _save(entries, path)
    return entries


def _window(day: date) -> set[date]:
    before = day - timedelta(days=1)
    while before.weekday() >= 5:
        before -= timedelta(days=1)
    span = (day - before).days
    return {before + timedelta(days=i) for i in range(span + 1)}


def blocking(today: date, entries: list[dict[str, str]]) -> str | None:
    """The label of the event that makes today a sit-out day, or None."""
    for entry in entries:
        try:
            if today in _window(date.fromisoformat(entry["date"])):
                return entry["label"]
        except ValueError:
            continue
    return None


def apply(regime: RegimeResult, today: date, entries: list[dict[str, str]]) -> RegimeResult:
    label = blocking(today, entries)
    if label is None:
        return regime
    return RegimeResult(
        label="event",
        bias=regime.bias,
        score=regime.score,
        confidence=max(regime.confidence, 1.0),
        reasons=(f"You marked {label} as a day to sit out.", *regime.reasons),
        missing=regime.missing,
    )
