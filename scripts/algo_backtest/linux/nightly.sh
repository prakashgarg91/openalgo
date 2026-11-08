#!/usr/bin/env bash
# Nightly chain for the option research data: the Linux equivalent of
# scripts/algo_backtest/windows/capture_option_candles.cmd.
#
# Read only: no step places an order. Like the .cmd, a failing step does not stop
# the steps after it, and the exit code of this script is the capture's exit code.
#
# Run by cron at 16:00 Monday to Friday (see crontab.example), or by hand:
#   scripts/algo_backtest/linux/nightly.sh
#
# Needs UPSTOX_ANALYTICS_TOKEN, either in the environment or as a line in .env.
# There is deliberately no "set -e": a later step must still run when an earlier one fails.
set -u

cd "$(dirname "$0")/../../.." || exit 1
mkdir -p log
LOG="log/capture.log"
# cron starts with a short PATH; uv is usually in one of these places.
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

echo "==== $(date '+%d-%m-%Y %H:%M:%S')" >> "$LOG"

# The token is checked here only so that a missing token is reported in the log.
# The file is searched for the name; its value is never read into this script.
if [ -z "${UPSTOX_ANALYTICS_TOKEN:-}" ] && ! grep -Eq '^[[:space:]]*UPSTOX_ANALYTICS_TOKEN[[:space:]]*=[[:space:]]*[^[:space:]]' .env 2>/dev/null; then
  echo "UPSTOX_ANALYTICS_TOKEN is not set in the environment or in .env. Add it to .env, then run this again. See docs/algos/always-on-server.md." >> "$LOG"
  exit 1
fi

# Save today's 1-minute candles of the active weekly Nifty options.
# Exit codes: 0 all saved (or a weekend); 2 a contract or the context failed; 3 a weekday with no Nifty candles.
uv run python scripts/algo_backtest/capture_option_candles.py >> "$LOG" 2>&1
CAPTURE_RESULT=$?
echo "capture exit code $CAPTURE_RESULT" >> "$LOG"

# Read what is stored and update the forward shadow test (read only).
uv run python scripts/algo_backtest/run_forward_s3n.py >> "$LOG" 2>&1

# Telegram alert for a failed capture, a missed day or a week that did not count.
uv run python scripts/algo_backtest/alert_forward.py "$CAPTURE_RESULT" >> "$LOG" 2>&1

# Forward ledgers for registered ideas, then the ETF ledgers and the Zen shadow follow ledger
# (it skips quietly if its file is missing).
uv run python scripts/algo_backtest/run_forward_eod.py >> "$LOG" 2>&1
uv run python scripts/algo_backtest/run_etf_ledgers.py >> "$LOG" 2>&1
uv run python scripts/algo_backtest/run_zen_follow.py >> "$LOG" 2>&1

# Check that the day's candles, VIX, ETF closes and report files arrived (Telegram alert if not).
uv run python scripts/algo_backtest/check_nightly.py >> "$LOG" 2>&1

# Last, a read-only copy of the finished day for other tools (db/snapshots).
uv run python scripts/algo_backtest/snapshot_historify.py >> "$LOG" 2>&1

exit "$CAPTURE_RESULT"
