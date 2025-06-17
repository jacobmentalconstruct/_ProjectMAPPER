@echo off
echo ============================
echo Launching ProjectMAPPER ...
echo ============================

REM Activate the conda environment
call conda activate mindshard

REM Run the updated main script from its new location
python src\projectmapper\main.py
