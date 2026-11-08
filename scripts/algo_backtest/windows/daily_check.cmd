@echo off
rem Runs the daily check (morning, midday or evening). Read only; places no order. Task Scheduler runs it Monday to Friday.
cd /d "%~dp0..\..\.."
if not exist log mkdir log
set SSLKEYLOGFILE=
uv run python scripts\algo_backtest\daily_check.py %1 >> log\daily_check_task.log 2>&1
exit /b %errorlevel%
