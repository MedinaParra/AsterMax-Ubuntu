@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0astermax-codeaster-runner.ps1" %*
exit /b %ERRORLEVEL%
