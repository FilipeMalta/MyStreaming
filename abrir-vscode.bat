@echo off
setlocal
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" (
  start "" "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" "%~dp0trilha.code-workspace"
  exit /b 0
)
if exist "%ProgramFiles%\Microsoft VS Code\Code.exe" (
  start "" "%ProgramFiles%\Microsoft VS Code\Code.exe" "%~dp0trilha.code-workspace"
  exit /b 0
)
where code >nul 2>nul
if not errorlevel 1 (
  call code "%~dp0trilha.code-workspace"
  exit /b 0
)
echo Abra o VS Code e selecione Arquivo - Abrir Workspace e escolha trilha.code-workspace.
pause
