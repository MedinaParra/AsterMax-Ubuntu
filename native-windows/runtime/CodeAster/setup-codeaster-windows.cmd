@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-codeaster-windows.ps1" %*
set "ASTERMAX_SETUP_EXIT=%ERRORLEVEL%"
if /I not "%~1"=="-Unattended" pause
exit /b %ASTERMAX_SETUP_EXIT%
