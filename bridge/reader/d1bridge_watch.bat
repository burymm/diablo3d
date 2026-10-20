@echo off
chcp 65001 >nul 2>&1
setlocal
title Diablo Bridge - reader (TH4 to GMod)
cd /d "%~dp0"

rem ============ self-elevation (keep this block ASCII-only) ============
net session >nul 2>&1
if errorlevel 1 goto elevate
goto have_admin

:elevate
echo Requesting administrator rights...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs" >nul 2>&1
exit /b

:have_admin
echo ==========================================================
echo    Diablo Bridge: reader TH4 -^> snapshot.json
echo    Out: D:\SteamLibrary\steamapps\common\GarrysMod\
echo         garrysmod\data\d1bridge\snapshot.json
echo    Stop: Ctrl+C in this window
echo ==========================================================
echo.

rem ============ python detection (ASCII-only) ============
set "PY="
where python >nul 2>&1 && set "PY=python"
if defined PY goto py_ok
set "PY=py"
where py >nul 2>&1 && goto py_ok
echo.
echo [ERROR] Python not found in PATH. Install Python 3 and add to PATH.
pause
exit /b 1

:py_ok
echo [OK] Python found.

rem ============ TH4 running? (instrumented build th43d.exe) ============
tasklist /FI "IMAGENAME eq th43d.exe" 2>nul | find /I "th43d.exe" >nul
if not errorlevel 1 goto th4_ok
echo.
echo [WARN] th43d.exe not found.
echo Please start the instrumented build: bridge\reader\run_th43d.bat
echo and enter the GAME, not the menu.
timeout /t 6 >nul
tasklist /FI "IMAGENAME eq th43d.exe" 2>nul | find /I "th43d.exe" >nul
if not errorlevel 1 goto th4_ok
echo.
echo [ERROR] Game still not running. Start it, then run this file again.
pause
exit /b 1

:th4_ok
echo [OK] th43d.exe running.

rem ============ offer to launch GMod ============
set "GQ=n"
set /p GQ="Launch Garry's Mod? [y/N] "
if /i "%GQ%"=="y" start "" "steam://rungameid/4000"

echo.
echo [Starting reader] Ctrl+C to stop.
echo Reverse channel is ON: reader executes clicks from
echo   garrysmod\data\d1bridge\bridge_cmd.json (GMod sends them).
echo NOTE: on every command the TH4 window is raised and takes focus.
echo ----------------------------------------------------------
"%PY%" d1reader.py watch --verbose --interval 0.1
echo ----------------------------------------------------------
echo.
echo [Done] Reader stopped.
pause