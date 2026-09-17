@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup_env.bat first.
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m src.app %*
set EXIT_CODE=%ERRORLEVEL%

endlocal & exit /b %EXIT_CODE%
