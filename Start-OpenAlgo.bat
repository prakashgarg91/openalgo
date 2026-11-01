@echo off
rem Starts OpenAlgo on this Windows computer and opens the login page. Double-click it each trading day.
rem
rem It works around an antivirus that scans secure connections (scripts\windows\start_openalgo.ps1 explains
rem how), starts the app in its own window, waits until the app answers, and opens your browser.
rem Close the "OpenAlgo server" window to stop the app. If the app is already running it only opens the browser.
title OpenAlgo launcher
cd /d "%~dp0"

powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/ -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel%==0 (
  echo OpenAlgo is already running.
  goto open
)

echo Starting OpenAlgo. This takes about a minute...
start "OpenAlgo server" cmd /k "%~dp0scripts\windows\start_openalgo.cmd"

powershell -NoProfile -Command "for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/ -TimeoutSec 3 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 2 } }; exit 1"
if not %errorlevel%==0 (
  echo.
  echo OpenAlgo did not start within two minutes. Look at the "OpenAlgo server" window for the reason,
  echo or send me what it says.
  pause
  exit /b 1
)

:open
start "" http://127.0.0.1:5000/login
echo.
echo OpenAlgo is open in your browser. Each trading day, in this order:
echo   1. Sign in to OpenAlgo with your username and password.
echo   2. Connect Upstox on the broker page (mobile number, one-time code, PIN). The Upstox login ends about 3:30 AM.
echo   3. Switch the badge at the top right to ANALYZE. After a broker login the app comes up in LIVE mode.
echo.
echo Keep the "OpenAlgo server" window open while you use the app. The 16:00 capture does not need it.
echo.
pause
