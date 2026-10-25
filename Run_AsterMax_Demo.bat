@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m astermax.windows_demo_runner --output astermax_demo_evidence
) else (
    python -m astermax.windows_demo_runner --output astermax_demo_evidence
)

if errorlevel 1 (
    echo.
    echo AsterMax demo failed. Review the console output above.
    pause
    exit /b 1
)

echo.
echo AsterMax demo evidence generated and verified.
echo Folder: %CD%\astermax_demo_evidence
pause
