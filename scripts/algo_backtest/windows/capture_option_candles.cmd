@echo off
rem Saves today's 1-minute candles for the active weekly Nifty options (read-only; places no order).
rem Run by the Windows task made by install_capture_task.cmd, or by hand.
rem Needs the user environment variable UPSTOX_ANALYTICS_TOKEN (set it once with: setx UPSTOX_ANALYTICS_TOKEN your-token).
cd /d "%~dp0..\..\.."
if not exist log mkdir log
echo ==== %date% %time% >> log\capture.log
if "%UPSTOX_ANALYTICS_TOKEN%"=="" (
  echo UPSTOX_ANALYTICS_TOKEN is not set for this Windows user. Run setx UPSTOX_ANALYTICS_TOKEN your-token once, then sign out and in. >> log\capture.log
  exit /b 1
)
uv run python scripts\algo_backtest\capture_option_candles.py >> log\capture.log 2>&1
exit /b %errorlevel%
