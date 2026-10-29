@echo off
rem Creates a Windows task that saves the weekly Nifty option candles every weekday at 16:00
rem (computer clock, so keep it on India time). Run once; run again to replace the task.
rem To remove it:  schtasks /delete /tn "OpenAlgo option capture" /f
rem To run it now: schtasks /run /tn "OpenAlgo option capture"
schtasks /create /tn "OpenAlgo option capture" /tr "\"%~dp0capture_option_candles.cmd\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 16:00 /f
if errorlevel 1 (
  echo The task was not created. Open this file as Administrator or check the message above.
  exit /b 1
)
echo Created. It runs Monday to Friday at 16:00 and writes to log\capture.log in the OpenAlgo folder.
echo The computer must be on, and you must be signed in, at that time.
