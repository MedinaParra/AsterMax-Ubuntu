@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-AsterMax-Demo.ps1"
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo AsterMax demo failed. Review the Logs folder for evidence.
  if defined CI (
    echo --- C8.78 launcher failure evidence ---
    for %%F in ("%~dp0Logs\launch-failure-*.json") do if exist "%%~fF" type "%%~fF"
    if exist "%~dp0Logs\AsterMax-demo.stderr.log" type "%~dp0Logs\AsterMax-demo.stderr.log"
    if exist "%~dp0Logs\AsterMax-demo.stdout.log" type "%~dp0Logs\AsterMax-demo.stdout.log"
    if defined GITHUB_WORKSPACE (
      if not exist "%GITHUB_WORKSPACE%\qualified-logs" mkdir "%GITHUB_WORKSPACE%\qualified-logs"
      xcopy /E /I /Y "%~dp0Logs" "%GITHUB_WORKSPACE%\qualified-logs" >nul
    )
  ) else (
    pause
  )
)
exit /b %RC%
