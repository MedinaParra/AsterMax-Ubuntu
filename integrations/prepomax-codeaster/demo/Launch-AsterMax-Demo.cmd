@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-AsterMax-Demo.ps1"
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo AsterMax demo failed. Review the Logs folder for evidence.
  if not defined CI pause
)
exit /b %RC%
