@echo off
setlocal EnableExtensions
title Zalo OCR Git Sync Tool

:: Always run from the folder containing this script
cd /d "%~dp0"

echo ==========================================================
echo Syncing Zalo OCR repository to GitHub...
echo ==========================================================
echo.

:: Add default Windows Git installation paths to PATH in case it's not set
set "PATH=%PATH%;%ProgramFiles%\Git\cmd;%ProgramFiles(x86)%\Git\cmd;%LocalAppData%\Programs\Git\cmd"

:: Check Git directly. Do not use "where" because some Windows PATH
:: configurations are missing System32 even though Git is installed.
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git is not installed or not found in system PATH.
    echo Please download and install Git from: https://git-scm.com/download/win
    echo.
    pause
    exit /b
)

:: Check if .git directory exists, if not initialize it
if not exist ".git" (
    echo Git repository not initialized. Initializing now...
    git init
    echo.
)

:: Configure local user identity for this repository
echo Configuring Git user identity...
git config user.email "duongminhhieu99@gmail.com"
git config user.name "Hhiieeuu1706"
echo Configured: Email=duongminhhieu99@gmail.com, Name=Hhiieeuu1706
echo.

:: Configure remote origin
echo Checking Git Remote Origin configuration...
git remote remove origin >nul 2>&1
git remote add origin https://github.com/Hhiieeuu1706/zaloOCR
echo Remote configured to: https://github.com/Hhiieeuu1706/zaloOCR
echo.

:: Add files to staging
echo Staging all changes...
git add .
echo.

:: Commit changes
echo Committing changes...
set "commit_msg=Auto sync: %date% %time%"
git commit -m "%commit_msg%"
echo.

:: Force push to main
echo Force-pushing repository to GitHub (main)...
git branch -M main
git push -u origin main --force
echo.

if errorlevel 1 (
    echo ==========================================================
    echo [WARNING] Sync failed. 
    echo Please make sure you have write permissions to the repository
    echo and your GitHub credentials/SSH keys are configured correctly.
    echo ==========================================================
) else (
    echo ==========================================================
    echo [SUCCESS] Synchronization complete!
    echo ==========================================================
)

echo.
pause
