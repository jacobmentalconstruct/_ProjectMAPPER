@echo off
setlocal EnableDelayedExpansion

REM === CONFIG ===
set MAIN_SCRIPT=_ProjectMAPPER.py

REM === RUN ===
echo [🚀] Running %MAIN_SCRIPT%...
python %MAIN_SCRIPT%

echo [🧹] Done.
pause
