@echo off
:: Prompt for GitHub repo URL securely
SET /P REPOURL="Enter GitHub repo URL (e.g., https://github.com/youruser/yourrepo.git): "

:: Initialize the git repo
git init

:: Create or update .gitignore
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
echo push_to_github.bat
) > .gitignore

:: Stage and commit everything except ignored
git add .
git commit -m "Initial commit"

:: Add remote
git remote add origin %REPOURL%

:: Detect current branch and push
git branch > temp.txt
findstr "main" temp.txt >nul && (
    git push -u origin main
) || (
    git push -u origin master
)
del temp.txt

echo === Push Complete ===
pause
