@echo off
rem 15:30 end-of-day summary of the ATM 200 Sandbox bot (read only; places no order). Sent to Telegram when the bot is on.
cd /d "%~dp0..\..\.."
if not exist log mkdir log
set SSLKEYLOGFILE=
echo ==== %date% %time% summary >> log\sandbox_summary.log
uv run python scripts\algo_backtest\sandbox_summary.py summary --notify >> log\sandbox_summary.log 2>&1
