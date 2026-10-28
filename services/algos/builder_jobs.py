"""Starting a builder search as a separate process and reading its answer.

One search at a time per installation: it is CPU heavy, and a second one would only
slow the first. The process writes to files in ``db/algo_builder/<job>/`` (never a
pipe), is reaped by a small waiter thread, and is killed if it overruns.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOB_ROOT = PROJECT_ROOT / "db" / "algo_builder"
TIMEOUT_SECONDS = 900
KEEP_JOBS = 10
_JOB_ID = re.compile(r"^[0-9a-f]{16}$")

_lock = threading.Lock()
_running: dict[str, subprocess.Popen] = {}


class Busy(Exception):
    """A search is already running."""


def valid_id(job_id: str) -> bool:
    return bool(_JOB_ID.match(job_id or ""))


def _prune() -> None:
    folders = sorted((p for p in JOB_ROOT.glob("*") if p.is_dir()), key=lambda p: p.stat().st_mtime)
    for old in folders[:-KEEP_JOBS]:
        if old.name not in _running:
            shutil.rmtree(old, ignore_errors=True)


def _wait(job_id: str, proc: subprocess.Popen) -> None:
    try:
        proc.wait(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        (JOB_ROOT / job_id / "error.json").write_text(
            json.dumps({"message": "The search took too long and was stopped. Try fewer options."})
        )
    finally:
        with _lock:
            _running.pop(job_id, None)


def start(user: str, request: dict[str, Any]) -> str:
    with _lock:
        if _running:
            raise Busy("A search is already running. It takes about a minute.")
        JOB_ROOT.mkdir(parents=True, exist_ok=True)
        _prune()
        job_id = secrets.token_hex(8)
        folder = JOB_ROOT / job_id
        folder.mkdir()
        (folder / "request.json").write_text(json.dumps({**request, "user": user}))
        with open(folder / "log.txt", "wb") as log:
            proc = subprocess.Popen(
                [sys.executable, "-m", "services.algos.builder_run", str(folder)],
                cwd=PROJECT_ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
        _running[job_id] = proc
    threading.Thread(target=_wait, args=(job_id, proc), daemon=True).start()
    return job_id


def _read(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def status(job_id: str, user: str) -> dict[str, Any] | None:
    """The job's state, or None when it is not this user's (or does not exist)."""
    if not valid_id(job_id):
        return None
    folder = JOB_ROOT / job_id
    request = _read(folder / "request.json")
    if not request or request.get("user") != user:
        return None
    result, error = _read(folder / "result.json"), _read(folder / "error.json")
    if result is not None:
        return {"state": "done", "result": result}
    if error is not None:
        return {"state": "failed", "message": error["message"]}
    if job_id in _running:
        return {"state": "running", "progress": _read(folder / "progress.json") or {"done": 0}}
    return {
        "state": "failed",
        "message": "The search was interrupted, for example by a restart. Run it again.",
    }
