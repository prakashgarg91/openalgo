"""Date ranges in the Historify service are exchange days: they start at India midnight on any computer."""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone

from services import historify_service as hs

IST = timezone(timedelta(hours=5, minutes=30))


def test_a_range_starts_at_india_midnight_of_its_first_day():
    expected = int(
        datetime(2026, 9, 30, 18, 30, tzinfo=UTC).timestamp()
    )  # 00:00 IST on 1 Oct
    assert hs._ist_day_start("2026-10-01") == expected
    assert hs._ist_day_start("2026-10-01", 1) == expected + 86400


def test_a_daily_bar_stamped_at_india_midnight_on_the_first_day_is_inside_the_range():
    bar = int(datetime(2026, 10, 1, 0, 0, tzinfo=IST).timestamp())
    assert bar >= hs._ist_day_start("2026-10-01")
    previous = int(datetime(2026, 9, 30, 0, 0, tzinfo=IST).timestamp())
    assert previous < hs._ist_day_start("2026-10-01")  # and the day before is outside it


def test_the_bounds_do_not_move_with_the_computers_timezone():
    code = (
        "from services import historify_service as h; print(h._ist_day_start('2026-10-01'), "
        "h._ist_day_start('2026-10-01', 1))"
    )
    answers = set()
    for zone in ("UTC", "Asia/Kolkata", "America/New_York"):
        run = subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "TZ": zone},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert run.returncode == 0, f"{zone}: {run.stderr[-500:]}"
        answers.add(run.stdout.strip().splitlines()[-1])
    assert len(answers) == 1
