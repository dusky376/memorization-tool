@echo off
REM ZhengZhi(politics) assistant - start LAN web server
REM ASCII only in this bat (cmd parses ANSI/GBK, not UTF-8)
cd /d %~dp0
echo Supporting info:
python server.py
pause
