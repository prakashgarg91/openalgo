"""Merge rules, staleness and the refresh run of the India VIX refresher, on made-up bars.

The HTTP client is a fake that returns Yahoo-shaped JSON, so nothing reaches the network. Every
file is written inside tmp_path.
"""

import importlib.util
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

IST_OFFSET = timedelta(hours=5, minutes=30)
IST = timezone(IST_OFFSET)
HEADER = "timestamp_utc,open,high,low,close,volume,adjclose\n"


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts/algo_backtest/refresh_vix.py"
    spec = importlib.util.spec_from_file_location("refresh_vix_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rv = _load_script()


def ist_at(day: str, hour: int = 9, minute: int = 15) -> datetime:
    """An India-time moment on the given YYYY-MM-DD."""
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00").replace(tzinfo=IST)


def bar_epoch(day: str) -> int:
    """Yahoo's stamp for a session: 09:15 IST, which is 03:45 UTC on the same date."""
    return int(ist_at(day).timestamp())


def old_frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    """A stored-style frame, as read_stored returns it, from (day, close) pairs."""
    index = [ist_at(day).astimezone(UTC).isoformat() for day, _ in rows]
    frame = pd.DataFrame({"close": [close for _, close in rows]}, index=index)
    frame.index.name = "timestamp_utc"
    return frame


def new_frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    """A fetch-style frame: UTC DatetimeIndex and the same column names fetch returns."""
    index = pd.to_datetime([ist_at(day).astimezone(UTC) for day, _ in rows], utc=True)
    frame = pd.DataFrame({"close": [close for _, close in rows]}, index=index)
    frame.index.name = "timestamp_utc"
    return frame


def stored_days(frame: pd.DataFrame) -> list[str]:
    return [stamp.astimezone(IST).date().isoformat() for stamp in frame.index]


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class FakeClient:
    """Stands in for httpx.Client: returns one canned response and records the calls."""

    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, params: dict | None = None) -> FakeResponse:
        self.calls.append((url, params or {}))
        return self.response


def chart_payload(rows: list[tuple[str, float]]) -> dict:
    """Yahoo v8 chart JSON for the given (day, close) bars."""
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [bar_epoch(day) for day, _ in rows],
                    "indicators": {
                        "quote": [
                            {
                                "open": [close for _, close in rows],
                                "high": [close for _, close in rows],
                                "low": [close for _, close in rows],
                                "close": [close for _, close in rows],
                                "volume": [0 for _ in rows],
                            }
                        ],
                        "adjclose": [{"adjclose": [close for _, close in rows]}],
                    },
                }
            ]
        }
    }


def write_stored(data_repo: Path, rows: list[tuple[str, float]]) -> Path:
    path = data_repo / "context" / "daily" / "_INDIAVIX.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [HEADER]
    for day, close in rows:
        stamp = ist_at(day).astimezone(UTC).isoformat()
        lines.append(f"{stamp},{close},{close},{close},{close},0,{close}\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def test_merge_keeps_stored_rows_and_adds_later_completed_sessions():
    old = old_frame([("2026-11-10", 14.0), ("2026-11-11", 14.5), ("2026-11-12", 15.0)])
    # 2026-11-12 is re-sent with a different close: the stored value must win.
    new = new_frame([("2026-11-12", 99.0), ("2026-11-13", 15.2), ("2026-11-16", 15.8)])

    merged = rv.merge_vix(old, new, ist_at("2026-11-17", 16, 0))

    assert stored_days(merged) == [
        "2026-11-10",
        "2026-11-11",
        "2026-11-12",
        "2026-11-13",
        "2026-11-16",
    ]
    assert merged["close"].tolist() == [14.0, 14.5, 15.0, 15.2, 15.8]
    assert merged.index.is_monotonic_increasing
    assert merged.index.is_unique


def test_merge_drops_today_bar_before_the_session_closes():
    old = old_frame([("2026-11-16", 15.0)])
    new = new_frame([("2026-11-17", 15.4), ("2026-11-18", 15.9)])

    before_close = rv.merge_vix(old, new, ist_at("2026-11-18", 11, 0))
    assert stored_days(before_close) == ["2026-11-16", "2026-11-17"]

    at_close = rv.merge_vix(old, new, ist_at("2026-11-18", 15, 45))
    assert stored_days(at_close) == ["2026-11-16", "2026-11-17", "2026-11-18"]


def test_merge_never_shrinks_when_new_data_is_older():
    old = old_frame([("2026-11-10", 14.0), ("2026-11-11", 14.5), ("2026-11-12", 15.0)])
    new = new_frame([("2026-11-09", 13.0), ("2026-11-10", 13.5)])

    merged = rv.merge_vix(old, new, ist_at("2026-11-17", 16, 0))

    assert len(merged) == len(old)
    assert merged["close"].tolist() == [14.0, 14.5, 15.0]


def test_merge_into_an_empty_old_file_takes_completed_new_bars_only():
    new = new_frame([("2026-11-16", 15.8), ("2026-11-17", 15.9), ("2026-11-18", 16.1)])

    merged = rv.merge_vix(pd.DataFrame(), new, ist_at("2026-11-18", 10, 0))

    assert stored_days(merged) == ["2026-11-16", "2026-11-17"]
    assert merged.index.name == "timestamp_utc"


def test_merge_is_idempotent_when_nothing_is_new():
    old = old_frame([("2026-11-16", 15.0), ("2026-11-17", 15.4)])
    new = new_frame([("2026-11-16", 15.0), ("2026-11-17", 15.4)])

    merged = rv.merge_vix(old, new, ist_at("2026-11-18", 10, 0))

    assert len(merged) == len(old)
    assert merged["close"].tolist() == [15.0, 15.4]


def test_staleness_counts_calendar_days_and_reports_empty_as_none():
    frame = old_frame([("2026-11-13", 15.0)])

    assert rv.staleness(frame, date(2026, 11, 18)) == 5
    assert rv.staleness(frame, date(2026, 11, 13)) == 0
    assert rv.staleness(pd.DataFrame(), date(2026, 11, 18)) is None


def test_read_stored_handles_missing_and_zero_byte_files(tmp_path):
    assert rv.read_stored(tmp_path / "absent.csv").empty

    empty = tmp_path / "zero.csv"
    empty.write_bytes(b"")
    assert rv.read_stored(empty).empty


def test_refresh_appends_new_bars_and_then_is_idempotent(tmp_path):
    path = write_stored(
        tmp_path, [("2026-11-10", 14.0), ("2026-11-11", 14.5), ("2026-11-12", 15.0)]
    )
    payload = chart_payload(
        [
            ("2026-11-12", 99.0),
            ("2026-11-13", 15.2),
            ("2026-11-16", 15.8),
            ("2026-11-17", 15.9),
            ("2026-11-18", 16.1),
        ]
    )
    client = FakeClient(FakeResponse(200, payload))

    assert rv.refresh(tmp_path, client, ist_at("2026-11-18", 11, 0), dry_run=False) == 0

    stored = pd.read_csv(path, index_col="timestamp_utc")
    assert stored["close"].tolist() == [14.0, 14.5, 15.0, 15.2, 15.8, 15.9]
    assert client.calls[0][1]["interval"] == "1d"
    assert client.calls[0][0].endswith("/^INDIAVIX")

    before = path.read_bytes()
    assert rv.refresh(tmp_path, client, ist_at("2026-11-18", 11, 0), dry_run=False) == 0
    assert path.read_bytes() == before


def test_refresh_dry_run_writes_nothing(tmp_path):
    path = write_stored(tmp_path, [("2026-11-16", 15.0)])
    before = path.read_bytes()
    client = FakeClient(FakeResponse(200, chart_payload([("2026-11-17", 15.4)])))

    assert rv.refresh(tmp_path, client, ist_at("2026-11-18", 11, 0), dry_run=True) == 0

    assert path.read_bytes() == before
    assert not path.with_name(path.name + ".tmp").exists()


def test_refresh_fetch_failure_keeps_the_old_file_and_exits_1(tmp_path, capsys):
    path = write_stored(tmp_path, [("2026-11-16", 15.0), ("2026-11-17", 15.4)])
    before = path.read_bytes()
    client = FakeClient(FakeResponse(500))

    assert rv.refresh(tmp_path, client, ist_at("2026-11-18", 11, 0), dry_run=False) == 1

    assert path.read_bytes() == before
    out = capsys.readouterr().out
    assert "left as it was" in out
    assert "2026-11-17" in out


def test_refresh_warns_and_exits_1_when_the_series_is_stale(tmp_path, capsys):
    path = write_stored(tmp_path, [("2026-11-10", 14.0)])
    client = FakeClient(FakeResponse(200, chart_payload([("2026-11-10", 14.0)])))

    code = rv.refresh(tmp_path, client, ist_at("2026-11-18", 11, 0), dry_run=False)

    assert code == 1
    assert "WARNING" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_refresh_creates_the_file_when_none_is_stored(tmp_path):
    client = FakeClient(FakeResponse(200, chart_payload([("2026-11-17", 15.4)])))

    code = rv.refresh(tmp_path, client, ist_at("2026-11-17", 16, 0), dry_run=False)

    assert code == 0
    stored = pd.read_csv(
        tmp_path / "context" / "daily" / "_INDIAVIX.csv", index_col="timestamp_utc"
    )
    assert stored["close"].tolist() == [15.4]


def test_main_refuses_a_path_that_is_not_a_folder(tmp_path, capsys):
    assert rv.main([str(tmp_path / "missing-repo")]) == 1
    assert "not a folder" in capsys.readouterr().out
