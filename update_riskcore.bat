@echo off
title RiskCore Update Tool
color 0F

echo.
echo  ==========================================
echo   RiskCore GRC Platform v1.5
echo   Update Tool
echo  ==========================================
echo.

REM ── Step 1: Copy new code files ──────────────────────────────────────────
echo  [1/2] Copying new code files...
echo.

set SOURCE=%~dp0
set DEST=%~dp0

robocopy "%SOURCE%" "%DEST%" /E ^
  /XF riskcore.db riskcore.db-shm riskcore.db-wal ^
      riskcore.log riskcore.key riskcore_apikey.txt ^
      settings.json update_riskcore.bat ^
  /XD backups __pycache__ .git dist build ^
  /NFL /NDL /NJH /NJS /NC /NS /NP

echo  Code files updated.
echo.

REM ── Step 2: Rebuild exe ───────────────────────────────────────────────────
echo  [2/2] Rebuilding executable...
echo.

py -m PyInstaller RiskCore.spec --noconfirm

echo.
echo  ==========================================
echo   Update complete!
echo.
echo   Your exe is ready at:
echo   dist\RiskCore\RiskCore.exe
echo.
echo   Your data (riskcore.db) is untouched.
echo  ==========================================
echo.
pause
