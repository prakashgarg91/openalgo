"""Registration-first record for the algo builder (docs/algos/TRIAL_REGISTER.md rules, made enforceable).

An idea is written down in full before anything runs. The record is frozen with a timestamp and a
hash, it counts toward one global trial count, and it can be run once. It can only be rejected or
made eligible for a forward test: nothing here says an edge is shown, and nothing here promotes.

Files only (one JSON and one markdown copy per registration in a folder), no database and no
network, so it needs no migration and is safe under eventlet, gthread and the dev server.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

#: Trials already counted in docs/algos/TRIAL_REGISTER.md: 311 to C1, plus the 8 reserved for the
#: December eight-structure screen (counted when it runs). Every registration adds its own on top.
SEED_TRIALS = 319
SIGNIFICANCE = 0.025
#: Months whose single idea slot is already taken by a registration made outside the builder.
SLOTS_USED = {"2026-11": "C1 month-end ETF window", "2026-12": "eight-structure screen"}

FIELDS = {
    "name": "a short name",
    "idea": "the idea in plain words",
    "instrument": "what is traded",
    "entry": "exactly when and how it enters",
    "exit": "exactly when and how it exits",
    "size": "how much, in whole lots or shares and rupees",
    "costs": "the cost schedule used and its doubled variant",
    "benchmark": "what it must beat (a hold of the same exposure, or cash)",
    "why_it_might_work": "why it could work",
    "how_it_fails": "the most likely way it fails",
    "data_seen": "which data periods have already been looked at",
    "data_unseen": "which data has never been looked at, and how it will be used once",
    "end_rule": "when the test ends (a date or a number of trades)",
    "kill_rule": "the loss at which it stops for good",
}
SUBMITTED = (*FIELDS, "gates", "params")


class Refused(Exception):
    """The registry declines; the message is written for the trader."""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "idea"


def _canonical(content: dict[str, Any]) -> str:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(content: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(content).encode("utf-8")).hexdigest()


def problems(draft: dict[str, Any]) -> list[str]:
    """What is missing or wrong in a draft, in words a trader can act on."""
    out = []
    for key, hint in FIELDS.items():
        value = draft.get(key)
        if not isinstance(value, str) or len(value.strip()) < 3:
            out.append(f"Write {key.replace('_', ' ')}: {hint}.")
    gates = draft.get("gates")
    if (
        not isinstance(gates, list)
        or not gates
        or not all(isinstance(g, str) and g.strip() for g in gates)
    ):
        out.append("List the gates it must pass, written now, one line each.")
    params = draft.get("params")
    if not isinstance(params, dict) or not params:
        out.append("Fix every setting to one value (name each one).")
    else:
        for name, value in params.items():
            if value is None or isinstance(value, (list, tuple, set, dict)):
                out.append(
                    f"Setting '{name}' has more than one value. Pick one: trying several is a search, "
                    "and every configuration tried counts as a trial."
                )
    trials = draft.get("trials", 1)
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
        out.append("Say how many trials this adds (a whole number, at least 1).")
    return out


def _store(folder: Path) -> list[dict[str, Any]]:
    found = []
    if folder.exists():
        for path in sorted(folder.glob("*.json")):
            found.append(json.loads(path.read_text(encoding="utf-8")))
    return found


def running_count(folder: Path) -> int:
    return SEED_TRIALS + sum(int(r["content"].get("trials", 1)) for r in _store(folder))


def pass_bar(count: int) -> float:
    """Significance divided by the running trial count, the bar a forward test must clear."""
    return SIGNIFICANCE / count


def _month(when: datetime) -> str:
    return f"{when:%Y-%m}"


def next_free_slot(folder: Path, now: datetime) -> str:
    taken = set(SLOTS_USED) | {r["slot"] for r in _store(folder)}
    year, month = now.year, now.month
    while f"{year}-{month:02d}" in taken:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return f"{year}-{month:02d}"


def register(draft: dict[str, Any], folder: Path, now: datetime) -> dict[str, Any]:
    """Freeze a draft. Refuses an incomplete draft, a month whose slot is used, and a duplicate."""
    issues = problems(draft)
    if issues:
        raise Refused(" ".join(issues))
    slot = _month(now)
    if slot in SLOTS_USED:
        raise Refused(
            f"This month's one new idea is already used by {SLOTS_USED[slot]}. "
            f"The next free month is {next_free_slot(folder, now)}."
        )
    for record in _store(folder):
        if record["slot"] == slot:
            raise Refused(
                f"This month's one new idea is already registered ({record['content']['name']}). "
                f"The next free month is {next_free_slot(folder, now)}."
            )
    content = {k: draft[k] for k in SUBMITTED if k in draft}
    content["trials"] = int(draft.get("trials", 1))
    digest = _hash(content)
    first = running_count(folder) + 1
    record = {
        "id": f"{_slug(content['name'])}-{digest[:8]}",
        "created_at": now.isoformat(timespec="seconds"),
        "slot": slot,
        "sha256": digest,
        "trial_numbers": [first, first + content["trials"] - 1],
        "pass_bar": pass_bar(first + content["trials"] - 1),
        "status": "registered",
        "run": None,
        "content": content,
    }
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{record['id']}.json"
    if target.exists():
        raise Refused(
            "This exact registration already exists. A changed idea is a new registration and a new trial."
        )
    _write(target, json.dumps(record, indent=2))
    _write(folder / f"{record['id']}.md", render(record))
    return record


def _write(path: Path, text: str) -> None:
    handle, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(text)
    os.replace(name, path)


def render(record: dict[str, Any]) -> str:
    c = record["content"]
    lines = [
        f"# {c['name']}: registered {record['created_at']}, before any run",
        "",
        f"Trial numbers {record['trial_numbers'][0]} to {record['trial_numbers'][1]}. "
        f"Pass bar: {SIGNIFICANCE} divided by {record['trial_numbers'][1]} = {record['pass_bar']:.6f}. "
        f"Fingerprint {record['sha256']}.",
        "",
    ]
    for key in FIELDS:
        lines += [f"## {key.replace('_', ' ').capitalize()}", c[key], ""]
    lines += ["## Gates", *[f"- {g}" for g in c["gates"]], "", "## Settings (one value each)"]
    lines += [f"- {k}: {v}" for k, v in c["params"].items()]
    return "\n".join(lines) + "\n"


def get(folder: Path, record_id: str) -> dict[str, Any] | None:
    path = folder / f"{record_id}.json"
    if not path.exists() or not re.fullmatch(r"[a-z0-9-]+", record_id):
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def intact(record: dict[str, Any]) -> bool:
    """True if the frozen content still matches its fingerprint (nothing was edited afterwards)."""
    return _hash(record["content"]) == record["sha256"]


def record_run(
    folder: Path, record_id: str, results: dict[str, bool], now: datetime
) -> dict[str, Any]:
    """Store the one run of a registration. A second run is refused. The only verdicts are
    'rejected' and 'eligible for a forward test'."""
    record = get(folder, record_id)
    if record is None:
        raise Refused("No such registration.")
    if not intact(record):
        raise Refused("This registration was changed after it was frozen, so it cannot be run.")
    if record["run"] is not None:
        raise Refused(
            "This registration has already been run. A second look is a new idea and a new trial."
        )
    gates = record["content"]["gates"]
    if set(results) != set(gates) or not all(isinstance(v, bool) for v in results.values()):
        raise Refused("Report a pass or fail for every registered gate, and no others.")
    failed = [g for g in gates if not results[g]]
    record["run"] = {
        "at": now.isoformat(timespec="seconds"),
        "results": results,
        "verdict": "rejected" if failed else "eligible for a forward test",
        "failed": failed,
    }
    record["status"] = "rejected" if failed else "eligible for a forward test"
    _write(folder / f"{record_id}.json", json.dumps(record, indent=2))
    return record
