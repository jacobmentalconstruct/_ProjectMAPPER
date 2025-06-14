@echo off
:: ========================================================================
:: Git Auto-Push Script (Pushes to GitHub and enforces 'main' branch)
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

:: Remove existing origin if present to avoid errors
git remote remove origin >nul 2>&1
git remote add origin %GITHUB_URL%

:: =====================[ BRANCH SYNC ]=========================
:: Rename 'master' to 'main' if needed
git branch > current_branch.tmp
findstr /C:"master" current_branch.tmp >nul
if %errorlevel%==0 (
    echo Renaming local 'master' branch to 'main'...
    git branch -m master main
)
del current_branch.tmp

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
git commit -m "Initial commit" >nul 2>&1

:: =====================[ PUSH TO MAIN ]========================
echo Pushing to remote 'main' branch...
git push -u origin main

:: =====================[ DONE ]================================
echo.
echo ✅ Push complete!
echo 🔗 Repo: %GITHUB_URL%
pause
