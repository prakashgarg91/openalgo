@echo off
rem One click: gets the research data onto this computer and keeps it up to date.
rem   1. clones or updates the private data repository next to the OpenAlgo folder (sign in to GitHub if asked)
rem   2. refreshes the foreign, sector and stock history (no token needed) and saves it to the repository
rem   3. resumes the Upstox expired-option download if UPSTOX_ANALYTICS_TOKEN is set (set it once with:
rem      setx UPSTOX_ANALYTICS_TOKEN your-token, then sign out and in). Finished expiries are skipped.
rem Read only towards Upstox and Yahoo; places no order. Output also goes to log\research_data.log.
cd /d "%~dp0..\..\.."
if not exist log mkdir log
set DATA=%CD%\..\openalgo-data
set SSLKEYLOGFILE=
echo ==== %date% %time% >> log\research_data.log
if exist "%DATA%\.git" (
  git -C "%DATA%" pull --rebase origin main >> log\research_data.log 2>&1
) else (
  git clone https://github.com/prakashgarg91/openalgo-data "%DATA%" >> log\research_data.log 2>&1
)
if errorlevel 1 (
  echo Could not reach the data repository. Check your GitHub sign-in and internet, then run this again.
  exit /b 1
)
uv run python scripts\algo_backtest\fetch_context_data.py "%DATA%" >> log\research_data.log 2>&1
git -C "%DATA%" add context bidask >> log\research_data.log 2>&1
git -C "%DATA%" commit -m "data: refresh foreign, sector and stock history" >> log\research_data.log 2>&1
git -C "%DATA%" push origin HEAD:main >> log\research_data.log 2>&1
if "%UPSTOX_ANALYTICS_TOKEN%"=="" (
  echo UPSTOX_ANALYTICS_TOKEN is not set, so the option download was skipped. Set it once with setx, then run this again.
  exit /b 0
)
uv run python scripts\algo_backtest\fetch_upstox_expired_all.py "%DATA%" 2024-10-01 2026-12-31 --sleep 1.0 >> log\research_data.log 2>&1
echo Done. The data is in %DATA%. Details are in log\research_data.log.
exit /b 0
