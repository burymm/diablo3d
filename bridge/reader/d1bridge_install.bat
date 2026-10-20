@echo off
chcp 65001 >nul 2>&1
setlocal
title Diablo Bridge - install GMod addon
cd /d "%~dp0"

set "SRC=%~dp0..\gmod\d1bridge.lua"
set "DST=D:\SteamLibrary\steamapps\common\GarrysMod\garrysmod\lua\autorun\client\d1bridge.lua"
set "GMOD=D:\SteamLibrary\steamapps\common\GarrysMod"
set "MODDIR=%GMOD%\garrysmod\lua\bin"
set "DLL_SRC=%~dp0..\gmod\d1bridge.dll"
set "DLL_DST=%MODDIR%\gmcl_d1bridge_win64.dll"

echo ==========================================================
echo    Diablo Bridge: install / update GMod addon
echo ==========================================================
echo.

set "PY="
where python >nul 2>&1 && set "PY=python"
if defined PY goto py_ok
set "PY=py"
where py >nul 2>&1 && goto py_ok
echo [ERROR] Python not found in PATH.
pause
exit /b 1

:py_ok
echo [OK] Python found.

if not exist "%SRC%" (
    echo [ERROR] Source not found: %SRC%
    pause
    exit /b 1
)

echo.
echo [1/2] Checking Lua syntax (no Lua interpreter needed)...
"%PY%" luacheck.py "%SRC%"
if errorlevel 1 (
    echo.
    echo [ABORT] Syntax check failed. Fix the file, then run this again.
    pause
    exit /b 1
)

echo.
echo [2/3] Copying addon to GMod...
if not exist "%GMOD%\garrysmod\lua\autorun\client" (
    echo [ERROR] GMod autorun folder not found. Is GMod installed at D:\SteamLibrary\...?
    pause
    exit /b 1
)
copy /y "%SRC%" "%DST%" >nul
if errorlevel 1 (
    echo [ERROR] Copy failed. Run this file as administrator.
    pause
    exit /b 1
)

echo [OK] Installed: %DST%

echo.
echo [3/3] Installing binary module (shared memory reader)...
if not exist "%DLL_SRC%" (
    echo [WARN] d1bridge.dll not built yet - run build_d1bridge_dll.bat
    echo        (addon will fall back to reading snapshot.json)
) else (
    if not exist "%MODDIR%" mkdir "%MODDIR%" >nul 2>&1
    copy /y "%DLL_SRC%" "%DLL_DST%" >nul
    if errorlevel 1 (
        echo [WARN] Could not copy module - close GMod and retry
    ) else (
        echo [OK] Installed: %DLL_DST%
    )
)

echo.
echo Reload in GMod: change map, or run in console:
echo   lua_openscript_cl "autorun/client/d1bridge.lua"
echo.
pause
