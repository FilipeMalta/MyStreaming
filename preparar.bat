@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import fastapi, uvicorn, telethon, cryptg" >nul 2>nul
  if not errorlevel 1 exit /b 0
)
where python >nul 2>nul
if errorlevel 1 (
  echo Instale Python 3.11 ou superior em https://www.python.org/downloads/ e marque Add Python to PATH.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 exit /b 1
echo Preparando as bibliotecas. A primeira execucao precisa de internet...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
type nul > ".venv\pronto"
exit /b 0
