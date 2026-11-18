"""A ledger folder rewritten in place every night must not look weeks old."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "algo_backtest"))


def test_a_folder_is_as_new_as_its_newest_file(tmp_path):
    import check_nightly as cn

    folder = tmp_path / "etf_ledger"
    folder.mkdir()
    old, fresh = folder / "a.csv", folder / "b.csv"
    old.write_text("x")
    fresh.write_text("y")
    long_ago = time.time() - 16 * 24 * 3600
    os.utime(old, (long_ago, long_ago))
    os.utime(folder, (long_ago, long_ago))  # rewriting a file in place leaves the folder time alone
    assert time.time() - cn.newest_mtime(folder) < 3600
    assert cn.newest_mtime(old) == old.stat().st_mtime
