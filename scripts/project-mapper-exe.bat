@echo off
echo ============================
echo Launching ProjectMAPPER ...
echo ============================

IF EXIST dist\ProjectMAPPER.exe (
    echo Running standalone executable...
    dist\ProjectMAPPER.exe
) ELSE (
    echo Running Python version in Conda environment...
    call conda activate mindshard
    python src\projectmapper\main.py
)
