@echo off
cd /d "%~dp0..\..\.."
set SSLKEYLOGFILE=
uv run python scripts\algo_backtest\ensure_analyze.py >> log\ensure_analyze.log 2>&1
exit /b 0
