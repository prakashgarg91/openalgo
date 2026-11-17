@echo off
rem Runs the Sandbox executor of the frozen ATM 200-wide rule: "entry" at 10:16, "check" every 5 minutes.
rem It refuses to place anything unless OpenAlgo is in Analyze mode. Usage: sandbox_bot_atm200.cmd entry|check
cd /d "%~dp0..\..\.."
if not exist log mkdir log
set SSLKEYLOGFILE=
echo ==== %date% %time% %1 >> log\sandbox_bot_atm200.log
uv run python scripts\algo_backtest\sandbox_bot_atm200.py %1 >> log\sandbox_bot_atm200.log 2>&1
