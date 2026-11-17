@echo off
rem Records the day's Sandbox account (read only; places no order). Run by the task "OpenAlgo record account".
cd /d "%~dp0..\..\.."
if not exist log mkdir log
set SSLKEYLOGFILE=
echo ==== %date% %time% >> log\record_account.log
uv run python scripts\algo_backtest\record_account.py D:\Github\openalgo-data >> log\record_account.log 2>&1
