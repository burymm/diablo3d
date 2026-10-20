@echo off
chcp 65001 >nul 2>&1
setlocal
title Diablo Bridge - reader tools
cd /d "%~dp0"

rem ============ self-elevation (ASCII-only) ============
net session >nul 2>&1
if errorlevel 1 goto elevate
goto have_admin

:elevate
echo Requesting administrator rights...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs" >nul 2>&1
exit /b

:have_admin
set "PY="
where python >nul 2>&1 && set "PY=python"
if defined PY goto py_ok
set "PY=py"
where py >nul 2>&1 && goto py_ok
echo.
echo [ERROR] Python not found in PATH.
pause
exit /b 1

:py_ok

:menu
cls
echo ==========================================================
echo    Diablo Bridge - reader tools
echo ==========================================================
echo  1) info       - show TH4 process/module (check)
echo  2) watch      - live read -^> snapshot.json  (main)
echo  3) bootstrap  - find hero by name, update offsets.json
echo  4) autofind   - find hero automatically (no name)
echo  5) hexdump    - dump memory at address
echo  6) findhero   - DIAG: find live hero by level+name (use if 3/4 read zeros)
echo  7) clicktest  - reverse channel: click in TH4 and measure latency
echo  0) Exit
echo ==========================================================
set "CH="
set /p "CH=Choose: "

if "%CH%"=="1" goto cmd_info
if "%CH%"=="2" goto cmd_watch
if "%CH%"=="3" goto cmd_bootstrap
if "%CH%"=="4" goto cmd_autofind
if "%CH%"=="5" goto cmd_hexdump
if "%CH%"=="6" goto cmd_findhero
if "%CH%"=="7" goto cmd_clicktest
if "%CH%"=="0" exit /b
goto menu

:cmd_info
echo.
"%PY%" d1reader.py info
pause
goto menu

:cmd_watch
echo.
echo Starting watch. Ctrl+C to stop.
"%PY%" d1reader.py watch --verbose --interval 0.1
pause
goto menu

:cmd_clicktest
echo.
echo [REVERSE CHANNEL] Click in the TH4 window via the reader,
echo then measure: did the hero move, and how fast.
echo Hero must be ALIVE and in the game. TH4 window takes focus.
echo.
set "CDIR=up"
set /p "CDIR=Screen direction [up]: "
set "CTILES=4"
set /p "CTILES=Tiles from center [4]: "
"%PY%" clicktest.py --dir "%CDIR%" --tiles %CTILES% --timeout 12
pause
goto menu

:cmd_bootstrap
echo.
set "PNAME="
set /p "PNAME=Hero name (as in game): "
if not defined PNAME goto menu
"%PY%" d1reader.py bootstrap --name "%PNAME%"
pause
goto menu

:cmd_autofind
echo.
"%PY%" d1reader.py autofind
pause
goto menu

:cmd_hexdump
echo.
set "PADDR="
set /p "PADDR=Address in hex, e.g. 0xDE7988: "
if not defined PADDR goto menu
set "PSIZE=256"
set /p "PSIZE=Size bytes [256]: "
if not defined PSIZE set "PSIZE=256"
"%PY%" d1reader.py hexdump --addr %PADDR% --size %PSIZE%
pause
goto menu

:cmd_findhero
echo.
echo [DIAG] Finds the LIVE hero by level + name in memory.
echo Make sure you are actually in the game first.
echo.
set "FNAME="
set /p "FNAME=Hero name: "
if not defined FNAME goto menu
set "FLEVEL="
set /p "FLEVEL=Hero level (int): "
if not defined FLEVEL goto menu
set "FHP="
set /p "FHP=Current HP as shown in game (blank = skip): "
if not defined FHP goto run_nohp
"%PY%" findhero.py --name "%FNAME%" --level %FLEVEL% --hp %FHP% --apply
pause
goto menu

:run_nohp
"%PY%" findhero.py --name "%FNAME%" --level %FLEVEL% --apply
pause
goto menu