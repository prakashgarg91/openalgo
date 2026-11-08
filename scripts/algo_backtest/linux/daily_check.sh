#!/usr/bin/env bash
# Runs the daily check (morning, midday or evening). Linux equivalent of
# scripts/algo_backtest/windows/daily_check.cmd. Read only: places no order.
#
# Usage:
#   scripts/algo_backtest/linux/daily_check.sh morning   (or midday, or evening)
# Cron runs it Monday to Friday at 09:20, 10:30 and 16:30 (see crontab.example).
set -u

cd "$(dirname "$0")/../../.." || exit 1
mkdir -p log
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

case "${1:-}" in
  morning|midday|evening) WHEN="$1" ;;
  *)
    echo "usage: $0 morning|midday|evening" >&2
    exit 2
    ;;
esac

uv run python scripts/algo_backtest/daily_check.py "$WHEN" >> log/daily_check_task.log 2>&1
exit $?
