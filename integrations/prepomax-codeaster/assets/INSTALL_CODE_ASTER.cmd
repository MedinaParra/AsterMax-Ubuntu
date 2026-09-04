@echo off
setlocal
title AsterMax Mechanical - Install Code_Aster
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-CodeAster-2025.ps1"
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo Code_Aster setup returned error %RC%.
) else (
  echo Code_Aster setup completed.
)
pause
exit /b %RC%
