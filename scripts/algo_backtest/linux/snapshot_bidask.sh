#!/usr/bin/env bash
# Saves one bid and ask snapshot of the active weekly Nifty options.
# Linux equivalent of scripts/algo_backtest/windows/snapshot_bidask.cmd. Read only: places no order.
#
# Usage:
#   scripts/algo_backtest/linux/snapshot_bidask.sh 1015   (or 1430, or 1500)
# Cron runs it at 10:15, 14:30 and 15:00 Monday to Friday (see crontab.example).
#
# Needs UPSTOX_ANALYTICS_TOKEN, either in the environment or as a line in .env, and the
# data repository at OPENALGO_DATA_REPO, or at $HOME/openalgo-data when that is not set.
set -u

cd "$(dirname "$0")/../../.." || exit 1
mkdir -p log
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

case "${1:-}" in
  1015|1430|1500) LABEL="$1" ;;
  *)
    echo "usage: $0 1015|1430|1500" >&2
    exit 2
    ;;
esac

LOG="log/bidask.log"
DATA_REPO="${OPENALGO_DATA_REPO:-$HOME/openalgo-data}"

echo "==== $(date '+%d-%m-%Y %H:%M:%S') $LABEL" >> "$LOG"

# The file is searched for the name only; its value is never read into this script.
if [ -z "${UPSTOX_ANALYTICS_TOKEN:-}" ] && ! grep -Eq '^[[:space:]]*UPSTOX_ANALYTICS_TOKEN[[:space:]]*=[[:space:]]*[^[:space:]]' .env 2>/dev/null; then
  echo "UPSTOX_ANALYTICS_TOKEN is not set in the environment or in .env. Add it to .env, then run this again. See docs/algos/always-on-server.md." >> "$LOG"
  exit 1
fi

if [ ! -d "$DATA_REPO" ]; then
  echo "The data repository is not at $DATA_REPO. Clone it there or set OPENALGO_DATA_REPO. See docs/algos/always-on-server.md." >> "$LOG"
  exit 1
fi

uv run python scripts/algo_backtest/snapshot_bidask.py "$DATA_REPO" "$LABEL" >> "$LOG" 2>&1
exit $?
