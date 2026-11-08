"""Daily check at three times on trading days, so a missed login or capture is seen in minutes.

    uv run python scripts/algo_backtest/daily_check.py morning|midday|evening [--no-alert]

Run by the Windows Task Scheduler. It reads OpenAlgo (running, API key, mode, a quote), the bid-ask
file, the nightly capture log and the Zen trade file, then prints one line per check and a headline,
appends the same text to log/daily_check.log and, when a check fails, sends a Telegram alert through
the OpenAlgo bot (skipped with --no-alert). It places no order. The API key is never printed or
written; the report shows only whether it is set.

Exit code 0 when no check failed, 1 otherwise.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from services.algos import daily_check as dc  # noqa: E402
from services.algos import forward_alerts as fa  # noqa: E402


def _load(name: str, path: Path):
    """Load a sibling script by path so its directory never lands on sys.path."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HERE = Path(__file__).resolve().parent
tc = _load("algo_thursday_check_script", HERE / "thursday_check.py")
dcomp = _load("algo_day_complete_script", HERE / "day_complete.py")

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_DATA_REPO = Path("D:/Github/openalgo-data")
DEFAULT_ZEN_FILE = Path(
    "D:/Github/trading-rex-ai/agent-results/stratzy-regime-study/trades/68596cd26aa2cba24bbb67da.jsonl"
)
CAPTURE_LOG = REPO / "log" / "capture.log"
LOG_FILE = Path("log") / "daily_check.log"


def data_repo() -> Path:
    return Path(os.getenv("OPENALGO_DATA_REPO") or DEFAULT_DATA_REPO)


def read_labels(day: date) -> set[str]:
    return dcomp.labels_in(data_repo() / "bidask" / f"{day.isoformat()}.csv")


def read_capture_text() -> str:
    if not CAPTURE_LOG.exists():
        return ""
    return (
        CAPTURE_LOG.read_text(encoding="utf-8", errors="replace")
        .replace("\r", "")
        .replace("\x00", "")
    )


def previous_weekday(day: date) -> date:
    prev = day - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


def read_yesterday_ok(today: date) -> bool:
    """True when the previous weekday's capture block is complete."""
    prev = previous_weekday(today)
    problems = dcomp.judge(read_capture_text(), prev, read_labels(prev), early=False)
    return not problems


def read_capture_problems(today: date) -> list[str]:
    return dcomp.judge(read_capture_text(), today, read_labels(today), early=False)


def read_zen_age_days(now: datetime) -> float | None:
    path = Path(os.getenv("ZEN_ADVICES_FILE") or DEFAULT_ZEN_FILE)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return max(0.0, (now.timestamp() - mtime) / 86400)


def read_openalgo(host: str) -> tuple[bool, bool, str | None, bool]:
    """(app_up, key_set, mode, quote_ok). The key value never leaves this function."""
    app = tc.app_up(host)
    key = tc.read_key()
    if not app or not key:
        return app, bool(key), None, False
    with httpx.Client(timeout=tc.TIMEOUT) as http:
        api = tc.bot_script.Api(http, host, key)
        mode = tc.read_mode(api)
        quote_ok = tc.read_spot(api) is not None
    return True, True, mode, quote_ok


def collect(when: str, now: datetime) -> dc.Facts:
    today = now.date()
    host = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")
    app, key, mode, quote_ok = (False, False, None, False)
    if when == "morning":
        app, key, mode, quote_ok = read_openalgo(host)
    else:
        app = tc.app_up(host)
        key = bool(tc.read_key())
    capture_problems = read_capture_problems(today) if when == "evening" else None
    return dc.Facts(
        when=when,
        today=today,
        app_up=app,
        key_set=key,
        mode=mode,
        quote_ok=quote_ok,
        snapshot_labels=read_labels(today),
        capture_problems=capture_problems,
        yesterday_capture_ok=read_yesterday_ok(today) if when == "morning" else None,
        zen_file_age_days=read_zen_age_days(now),
    )


def alert_text(when: str, today: date, rows: list[tuple[str, str, str]], headline: str) -> str:
    failing = [f"{check}: {message}" for level, check, message in rows if level == "fail"]
    return f"Daily check ({when}, {today:%a %d %b}): {headline} " + " ".join(failing)


def append_log(lines: list[str], now: datetime) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(f"{stamp} {line}\n")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    no_alert = "--no-alert" in args
    whens = [a for a in args if not a.startswith("--")]
    if len(whens) != 1 or whens[0] not in dc.WHENS:
        print(__doc__)
        return 2
    when = whens[0]

    now = datetime.now(IST)
    facts = collect(when, now)
    rows = dc.evaluate(facts)
    headline = dc.headline(rows)

    lines = [f"Daily check ({when}) for {facts.today}"]
    lines += [f"[{level.upper():4}] {check}: {message}" for level, check, message in rows]
    lines.append(headline)
    for line in lines:
        print(line)
    append_log(lines, now)

    if dc.should_alert(rows) and not no_alert:
        try:
            sent = fa.notify(alert_text(when, facts.today, rows, headline))
            if not sent:
                print("Telegram alert was not sent (the bot may be off); see log/daily_check.log.")
        except Exception:
            print("Telegram alert could not be sent; the problems are in log/daily_check.log.")

    return 0 if not any(level == "fail" for level, _, _ in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
