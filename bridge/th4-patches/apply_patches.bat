@echo off
chcp 65001 >nul 2>&1
setlocal
title Diablo Bridge - apply TH4 patches
cd /d "%~dp0..\..\vendor\the-hell-4-src"

if not exist ".git" (
    echo [ERROR] %CD% is not a git repository - run: git submodule update --init
    pause
    exit /b 1
)

rem Патч записан с LF, а checkout submodule может быть с CRLF (autocrlf=true).
rem Поэтому сначала пробуем строгое применение, затем --ignore-whitespace.
set "PATCH=%~dp00001-th4-shm-bridge.patch"

echo ==========================================================
echo    Diablo Bridge: apply patches to TH4 sources
echo ==========================================================
echo.
echo Target : %CD%
echo Patch  : %PATCH%
echo.

git apply --check "%PATCH%" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Strict check failed, retrying with --ignore-whitespace...
    git apply --check --ignore-whitespace "%PATCH%" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Patch does not apply cleanly.
        echo        Maybe it is already applied? Check: git -C "%CD%" status
        pause
        exit /b 1
    )
    git apply --ignore-whitespace "%PATCH%"
) else (
    git apply "%PATCH%"
)

if errorlevel 1 (
    echo [ERROR] git apply failed
    pause
    exit /b 1
)

echo [OK] Patch applied.
echo.
echo Changed files:
git -C "%CD%" status --short
echo.
echo Next: build th43d.exe  (bridge\reader\build_th43d.bat)
pause
