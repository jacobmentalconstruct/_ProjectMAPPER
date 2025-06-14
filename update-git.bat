@echo off
:: ========================================================================
:: Git Auto-Push Script (Main-Only, for clean single-branch projects)
:: ========================================================================

:: =====================[ GLOBAL CONFIG ]=======================
setlocal enabledelayedexpansion
set "SCRIPT_NAME=update-git.bat"
set "GITHUB_URL="

:: =====================[ USER INPUT ]==========================
if "%GITHUB_URL%"=="" (
    set /P GITHUB_URL=Enter GitHub repo URL (example: https://github.com/user/repo.git^) ^
:
)

:: =====================[ INIT GIT + REMOTE ]===================
echo Initializing Git repository...
git init >nul 2>&1

:: Ensure only correct remote
git remote remove origin >nul 2>&1
git remote add origin %GITHUB_URL%

:: =====================[ .GITIGNORE SETUP ]====================
echo Creating/updating .gitignore...
(
    echo __pycache__/
    echo *.pyc
    echo *.log
    echo .env
    echo *.db
    echo _logs/
    echo *.rar
    echo .vscode/
    echo .idea/
    echo %SCRIPT_NAME%
) > .gitignore

:: =====================[ STAGE + COMMIT ]======================
echo Staging and committing files...
git add .
git commit -m "Update project files" >nul 2>&1

:: =====================[ FORCE PUSH TO MAIN ]==================
echo Pushing to remote 'main' branch (forced)...
git push --force -u origin main

:: =====================[ DONE ]================================
echo.
echo ✅ Push complete!
echo 🔗 Repo: %GITHUB_URL%
pause
