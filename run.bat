@echo off
setlocal

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup_env.bat first.
    exit /b 1
)

set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
"%~dp0.venv\Scripts\python.exe" -m projectmapper %*
set EXIT_CODE=%ERRORLEVEL%

endlocal & exit /b %EXIT_CODE%
