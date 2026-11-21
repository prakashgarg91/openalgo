@echo off
rem Weekday 16:00 end of day (owner's choice, 21 Nov 2026): capture the day's option candles, save the
rem day to the data repository, then switch the computer off about 3 minutes later whatever the result.
rem Replaces the separate 16:00 capture task, so the capture always finishes before the shutdown.
rem Cancel a pending shutdown with: shutdown /a
cd /d "%~dp0..\..\.."
if not exist log mkdir log
echo ==== %date% %time% end of day with shutdown >> log\finish_day.log
call "%~dp0capture_option_candles.cmd"
call "%~dp0finish_day.cmd"
shutdown /a >nul 2>&1
shutdown /s /t 180 /c "OpenAlgo: end of day, switching off in 3 minutes. Cancel with: shutdown /a"
