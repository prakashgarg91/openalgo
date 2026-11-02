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
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)
#: Registering and counting are read-modify-write: one at a time within a process.
_LOCK = threading.Lock()
MAX_TRIALS_PER_REGISTRATION = 100

#: Trials already counted in docs/algos/TRIAL_REGISTER.md: 311 to C1, plus the 8 reserved for the
#: December eight-structure screen (counted when it runs). Every registration adds its own on top.
SEED_TRIALS = 319
SIGNIFICANCE = 0.025
BUILDER_TRIALS_FILE = "builder_trials.json"
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


NEAR_DUPLICATE = 0.6  # share of words two ideas must have in common to count as the same idea
_WORDS = re.compile(r"[a-z0-9]+")
_STOP = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "and",
    "or",
    "in",
    "on",
    "at",
    "is",
    "it",
    "for",
    "with",
    "by",
}


def _words(text: str) -> set[str]:
    return {w for w in _WORDS.findall(text.lower()) if w not in _STOP and len(w) > 1}


def near_duplicate(draft: dict[str, Any], folder: Path) -> str | None:
    """The name of a registered idea this draft restates, or None. A reworded idea is the same idea."""
    mine = _words(f"{draft.get('name', '')} {draft.get('idea', '')} {draft.get('entry', '')}")
    if not mine:
        return None
    for record in _store(folder):
        c = record["content"]
        theirs = _words(f"{c['name']} {c['idea']} {c['entry']}")
        if theirs and len(mine & theirs) / len(mine | theirs) >= NEAR_DUPLICATE:
            return str(c["name"])
    return None


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
            if isinstance(value, str) and re.search(r"[,;|]|\.\.|\bto\b", value):
                out.append(
                    f"Setting '{name}' looks like several values or a range. Pick one: trying "
                    "several is a search, and every configuration tried counts as a trial."
                )
            elif value is None or isinstance(value, (list, tuple, set, dict)):
                out.append(
                    f"Setting '{name}' has more than one value. Pick one: trying several is a search, "
                    "and every configuration tried counts as a trial."
                )
    trials = draft.get("trials", 1)
    if (
        isinstance(trials, bool)
        or not isinstance(trials, int)
        or not 1 <= trials <= MAX_TRIALS_PER_REGISTRATION
    ):
        out.append(
            f"Say how many trials this adds (a whole number from 1 to {MAX_TRIALS_PER_REGISTRATION})."
        )
    return out


def _store(folder: Path) -> list[dict[str, Any]]:
    found = []
    if folder.exists():
        for path in sorted(folder.glob("*.json")):
            if path.name == BUILDER_TRIALS_FILE:
                continue
            try:
                found.append(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                logger.exception("Skipping an unreadable registration file: %s", path.name)
    return found


def add_builder_trials(folder: Path, count: int, source: str, now: datetime) -> None:
    """Count the configurations a builder search tried. Every one is a trial, whatever the verdict."""
    if count <= 0:
        return
    path = folder / BUILDER_TRIALS_FILE
    with _LOCK:
        entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        entries.append(
            {"at": now.isoformat(timespec="seconds"), "source": source, "trials": int(count)}
        )
        folder.mkdir(parents=True, exist_ok=True)
        _write(path, json.dumps(entries, indent=2))


def builder_trials(folder: Path) -> int:
    path = folder / BUILDER_TRIALS_FILE
    if not path.exists():
        return 0
    return sum(int(e["trials"]) for e in json.loads(path.read_text(encoding="utf-8")))


def running_count(folder: Path) -> int:
    registered = sum(int(r["content"].get("trials", 1)) for r in _store(folder))
    return SEED_TRIALS + registered + builder_trials(folder)


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


def register(
    draft: dict[str, Any],
    folder: Path,
    now: datetime,
    known_algo_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Freeze a draft. Refuses an incomplete draft, a month whose slot is used, and a duplicate.

    One at a time: the month check, the trial numbers and the write are one step, so two quick
    submissions cannot both pass the check or share trial numbers.
    """
    with _LOCK:
        return _register(draft, folder, now, known_algo_ids)


def _register(
    draft: dict[str, Any], folder: Path, now: datetime, known_algo_ids: set[str] | None
) -> dict[str, Any]:
    issues = problems(draft)
    twin = near_duplicate(draft, folder)
    if twin:
        issues.append(
            f"This restates an idea already registered ({twin}). A reworded idea is the same idea."
        )
    named = (draft.get("params") or {}).get("algo_id")
    if named is not None and known_algo_ids is not None and named not in known_algo_ids:
        issues.append(
            "The algo named in the settings (algo_id) is not one of the algos in this app."
        )
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


def engine_seal(
    registration_sha256: str, results: dict[str, bool], source: str = "eod_screen"
) -> str:
    """The seal a rejection-screen engine attaches to the gate results it computed for one frozen
    registration. ``record_run`` refuses results without it, so a hand-typed pass is not accepted
    by mistake. It guards against slips and against an agent or page writing results; it does not
    stop someone with the server's files from forging one, and is not meant to."""
    text = _canonical({"sha": registration_sha256, "results": results, "source": source, "v": 1})
    return hashlib.sha256(("engine-seal:" + text).encode("utf-8")).hexdigest()


def record_run(
    folder: Path, record_id: str, results: dict[str, bool], now: datetime, seal: str | None = None
) -> dict[str, Any]:
    """Store the one run of a registration. A second run is refused. The only verdicts are
    'rejected' and 'eligible for a forward test'."""
    record = get(folder, record_id)
    if record is None:
        raise Refused("No such registration.")
    if not intact(record):
        raise Refused("This registration was changed after it was frozen, so it cannot be run.")
    if seal != engine_seal(record["sha256"], results):
        raise Refused(
            "These gate results did not come from the screen engine, so they were not recorded."
        )
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


FORWARD_VERDICTS = ("pass", "fail", "inconclusive")


def record_forward(
    folder: Path, record_id: str, verdict: str, evidence: dict[str, Any], now: datetime
) -> dict[str, Any]:
    """Store the end of a forward test. Only a registration that was run and found eligible can have
    one, and it can be recorded once. A pass here is what the optional Live requirement looks for."""
    record = get(folder, record_id)
    if record is None:
        raise Refused("No such registration.")
    if verdict not in FORWARD_VERDICTS:
        raise Refused("The forward verdict must be pass, fail or inconclusive.")
    if not intact(record):
        raise Refused(
            "This registration was changed after it was frozen, so no result can be recorded."
        )
    if record.get("forward") is not None:
        raise Refused("The forward result of this registration is already recorded.")
    if record["status"] != "eligible for a forward test":
        raise Refused(
            "Only a registration found eligible for a forward test can have a forward result."
        )
    record["forward"] = {
        "at": now.isoformat(timespec="seconds"),
        "verdict": verdict,
        "evidence": evidence,
    }
    record["status"] = f"forward {verdict}"
    _write(folder / f"{record_id}.json", json.dumps(record, indent=2))
    return record


MIN_POST_MORTEM_CHARS = 60


def needs_post_mortem(record: dict[str, Any]) -> bool:
    """True for a finished forward test whose written post-mortem is still owed."""
    forward = record.get("forward")
    return bool(forward) and not forward.get("post_mortem")


def add_post_mortem(folder: Path, record_id: str, text: str, now: datetime) -> dict[str, Any]:
    """The owner's written account of what a forward test showed and what it did not. A forward pass
    counts toward Live only once it has one, so the result is read before it is relied on."""
    record = get(folder, record_id)
    if record is None:
        raise Refused("No such registration.")
    if record.get("forward") is None:
        raise Refused("A post-mortem is written after the forward test has ended.")
    if record["forward"].get("post_mortem"):
        raise Refused("A post-mortem is already recorded for this registration.")
    if not isinstance(text, str) or len(text.strip()) < MIN_POST_MORTEM_CHARS:
        raise Refused(
            f"Write at least {MIN_POST_MORTEM_CHARS} characters: what it showed, what it cannot "
            "show, and what you would do differently."
        )
    record["forward"]["post_mortem"] = {
        "at": now.isoformat(timespec="seconds"),
        "text": text.strip(),
    }
    _write(folder / f"{record_id}.json", json.dumps(record, indent=2))
    return record


def forward_passed(folder: Path, algo_id: str) -> bool:
    """True if a registration naming this algo (its ``algo_id`` setting) has a recorded forward pass."""
    return any(
        r["content"]["params"].get("algo_id") == algo_id
        and (r.get("forward") or {}).get("verdict") == "pass"
        and bool((r.get("forward") or {}).get("post_mortem"))
        and intact(r)
        for r in _store(folder)
    )
