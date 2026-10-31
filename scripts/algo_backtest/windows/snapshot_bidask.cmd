@echo off
rem Saves one bid and ask snapshot of the active weekly Nifty options (read only; places no order).
rem Run by the Windows tasks made by install_bidask_tasks.cmd, or by hand:  snapshot_bidask.cmd 1015
rem Needs the user environment variable UPSTOX_ANALYTICS_TOKEN (set once with: setx UPSTOX_ANALYTICS_TOKEN your-token)
rem and the data repository cloned next to the OpenAlgo folder (download_research_data.cmd does that).
cd /d "%~dp0..\..\.."
if not exist log mkdir log
set LABEL=%1
if "%LABEL%"=="" set LABEL=manual
echo ==== %date% %time% %LABEL% >> log\bidask.log
if "%UPSTOX_ANALYTICS_TOKEN%"=="" (
  echo UPSTOX_ANALYTICS_TOKEN is not set for this Windows user. Run setx UPSTOX_ANALYTICS_TOKEN your-token once, then sign out and in. >> log\bidask.log
  exit /b 1
)
if not exist "%CD%\..\openalgo-data" (
  echo The data repository is not next to the OpenAlgo folder. Run download_research_data.cmd first. >> log\bidask.log
  exit /b 1
)
rem Some antivirus programs (Avast) set SSLKEYLOGFILE to one of their own devices, which makes Python exit
rem silently the moment it opens a secure connection. Clear it for this run only.
set SSLKEYLOGFILE=
uv run python scripts\algo_backtest\snapshot_bidask.py "%CD%\..\openalgo-data" %LABEL% >> log\bidask.log 2>&1
exit /b %errorlevel%
