@echo off
rem Archives public market headlines with the time first seen (read only). Run by the task "OpenAlgo news archive".
cd /d "%~dp0..\..\.."
if not exist log mkdir log
set SSLKEYLOGFILE=
uv run python scripts\algo_backtest\archive_news.py D:\Github\openalgo-data >> log\news_archive.log 2>&1
