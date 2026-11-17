@echo off
rem Records the day's Sandbox account (read only; places no order). Run by the task "OpenAlgo record account".
cd /d "%~dp0..\..\.."
if not exist log mkdir log
set SSLKEYLOGFILE=
echo ==== %date% %time% >> log\record_account.log
uv run python scripts\algo_backtest\record_account.py D:\Github\openalgo-data >> log\record_account.log 2>&1
rem Exploratory log of what the frozen 200-wide rule would have done on the stored snapshots (read only, counts for nothing).
uv run python scripts\algo_backtest\atm200_signal_log.py D:\Github\openalgo-data >> log\record_account.log 2>&1
