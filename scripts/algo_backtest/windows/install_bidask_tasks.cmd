@echo off
rem Creates three Windows tasks that save a bid and ask snapshot every weekday at 10:15, 14:30 and 15:00
rem (computer clock, so keep it on India time). Run once; run again to replace them.
rem To remove them:  schtasks /delete /tn "OpenAlgo bid-ask 1015" /f   (and 1430, 1500)
rem To run one now:  schtasks /run /tn "OpenAlgo bid-ask 1015"
set FAILED=0
call :make 1015 10:15
call :make 1430 14:30
call :make 1500 15:00
if "%FAILED%"=="1" (
  echo A task was not created. Open this file as Administrator or check the message above.
  exit /b 1
)
echo Created. They run Monday to Friday at 10:15, 14:30 and 15:00 and write to log\bidask.log in the OpenAlgo folder.
echo The computer must be on, and you must be signed in, at those times.
exit /b 0
:make
schtasks /create /tn "OpenAlgo bid-ask %1" /tr "\"%~dp0snapshot_bidask.cmd\" %1" /sc weekly /d MON,TUE,WED,THU,FRI /st %2 /f
if errorlevel 1 set FAILED=1
exit /b 0
