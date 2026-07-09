@echo off
title RiskCore — Build Release Package
color 0F

echo.
echo  ==========================================
echo   RiskCore v1.5 — Build Release Package
echo  ==========================================
echo.

REM ── Step 1: Install dependencies ──────────────────────────────────────────
echo  [1/3] Installing build dependencies...
py -m pip install pyinstaller pillow --quiet
echo  Done.
echo.

REM ── Step 2: Build the exe ─────────────────────────────────────────────────
echo  [2/3] Building executable (this takes 2-5 minutes)...
py -m PyInstaller RiskCore.spec --noconfirm --clean
echo.

REM ── Check build succeeded ─────────────────────────────────────────────────
if not exist "dist\RiskCore.exe" (
    echo  ERROR: Build failed. Check output above for errors.
    pause
    exit /b 1
)

echo  Build successful!
echo.

REM ── Step 3: Create release package ────────────────────────────────────────
echo  [3/3] Creating release package...

set RELEASE_DIR=RiskCore_v1.5_Windows
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"

copy "dist\RiskCore.exe" "%RELEASE_DIR%\RiskCore.exe" >nul
copy "README_QUICKSTART.txt" "%RELEASE_DIR%\README_QUICKSTART.txt" >nul

REM Create zip using PowerShell
powershell -Command "Compress-Archive -Path '%RELEASE_DIR%\*' -DestinationPath 'RiskCore_v1.5_Windows.zip' -Force"

echo.
echo  ==========================================
echo   Release package ready!
echo.
echo   Folder:  %RELEASE_DIR%\
echo   Zip:     RiskCore_v1.5_Windows.zip
echo.
echo   Contents:
echo     RiskCore.exe          (main application)
echo     README_QUICKSTART.txt (user guide)
echo.
echo   Upload RiskCore_v1.5_Windows.zip to:
echo   GitHub ^> Releases ^> v1.5 ^> Assets
echo  ==========================================
echo.
pause
