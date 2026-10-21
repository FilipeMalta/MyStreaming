@echo off
setlocal
cd /d "%~dp0"
call preparar.bat
if errorlevel 1 goto fim
echo.
echo TRILHA - Abra http://127.0.0.1:8765 no navegador.
echo Mantenha esta janela aberta. Para encerrar, pressione Ctrl+C.
".venv\Scripts\python.exe" run_local.py
:fim
pause
