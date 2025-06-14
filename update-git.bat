@echo off
:: ========================================================================
:: Git Auto-Push Script for Single Project Repos
:: ========================================================================

:: =====================[ GLOBAL CONFIG ]=======================
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

git remote remove origin >nul 2>&1
git remote add origin %GITHUB_URL%

:: =====================[ .GITIGNORE ]==========================
echo Generating .gitignore...
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

:: =====================[ COMMIT & PUSH ]=======================
echo Staging and committing...
git add .
git commit -m "Initial commit" >nul 2>&1

echo Pushing to remote...
git branch > _branch.tmp
findstr /C:"main" _branch.tmp >nul && (
    git push -u origin main
) || (
    git push -u origin master
)
del _branch.tmp

:: =====================[ DONE ]================================
echo.
echo ✅ Push complete!
echo 🔗 Repo: %GITHUB_URL%
pause
