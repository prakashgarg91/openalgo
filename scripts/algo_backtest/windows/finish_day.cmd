@echo off
rem End of the trading day: if every part of today's run is in place, save the bid-ask files to the data
rem repository and switch the computer off after 5 minutes (cancel with: shutdown /a). Otherwise leave it on.
cd /d "%~dp0..\..\.."
set SSLKEYLOGFILE=
set DATAREPO=D:\Github\openalgo-data
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
echo ==== finish_day %TODAY% %time% >> log\finish_day.log
uv run python scripts\algo_backtest\day_complete.py %DATAREPO% %TODAY% %1 >> log\finish_day.log 2>&1
if errorlevel 1 (
  echo Day not complete: computer left on. >> log\finish_day.log
  exit /b 1
)
git -C %DATAREPO% add bidask >> log\finish_day.log 2>&1
git -C %DATAREPO% commit -m "data: bid-ask snapshots %TODAY%" >> log\finish_day.log 2>&1
git -C %DATAREPO% pull --rebase >> log\finish_day.log 2>&1
git -C %DATAREPO% push >> log\finish_day.log 2>&1
if errorlevel 1 (
  echo Data push failed: computer left on. >> log\finish_day.log
  exit /b 2
)
echo Shutting down in 300 seconds. >> log\finish_day.log
shutdown /s /t 300 /c "OpenAlgo day complete. Cancel with: shutdown /a"
