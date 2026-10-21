@echo off
setlocal
cd /d "%~dp0"
call preparar.bat
if errorlevel 1 goto fim
".venv\Scripts\python.exe" connect.py
:fim
pause
