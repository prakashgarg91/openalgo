@echo off
rem Starts OpenAlgo on Windows, working around an antivirus that scans secure connections (see start_openalgo.ps1).
rem Double-click it, or run it from a terminal. It stays open while the app runs; close the window to stop it.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_openalgo.ps1" %*
