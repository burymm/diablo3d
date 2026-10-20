@echo off
chcp 65001 >nul 2>&1
setlocal
title Diablo Bridge - build GMod Lua module
cd /d "%~dp0"

set "MSBUILD=C:\Program Files\Microsoft Visual Studio\18\Community\MSBuild\Current\Bin\MSBuild.exe"
set "GMOD=D:\SteamLibrary\steamapps\common\GarrysMod"
set "LUA32=%GMOD%\garrysmod\bin\lua_shared.dll"
set "LUA64=%GMOD%\garrysmod\bin\win64\lua_shared.dll"

set "DUMPBIN=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.50.35717\bin\Hostx64\x64\dumpbin.exe"
set "LIB32=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.50.35717\bin\Hostx64\x86\lib.exe"
set "LIB64=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.50.35717\bin\Hostx64\x64\lib.exe"

echo ==========================================================
echo    Diablo Bridge: build d1bridge.dll -- GMod Lua module
echo ==========================================================
echo.

if not exist "%MSBUILD%" goto no_msbuild
if not exist "%DUMPBIN%" goto no_msbuild

echo [1/3] Generating import libraries from GMod lua_shared.dll...

if exist "%LUA32%" goto have32
echo [WARN] x86 lua_shared.dll not found
goto after32

:have32
call :make_def "%LUA32%" lua32_exports.txt lua32_shared.def
"%LIB32%" /DEF:lua32_shared.def /OUT:lua_shared.lib /MACHINE:X86 >nul 2>&1
echo [OK] lua_shared.lib -- x86

:after32
if exist "%LUA64%" goto have64
echo [WARN] x64 lua_shared.dll not found
goto after64

:have64
call :make_def "%LUA64%" lua64_exports.txt lua64_shared.def
"%LIB64%" /DEF:lua64_shared.def /OUT:lua64_shared.lib /MACHINE:X64 >nul 2>&1
echo [OK] lua64_shared.lib -- x64

:after64
echo.
echo [2/3] Building...
"%MSBUILD%" d1bridge_dll.vcxproj /p:Configuration=Release /p:Platform=Win32 /v:minimal
if errorlevel 1 goto build_fail
"%MSBUILD%" d1bridge_dll.vcxproj /p:Configuration=Release /p:Platform=x64 /v:minimal
if errorlevel 1 goto build_fail

echo.
echo [3/3] Selecting build for this GMod...
REM GMod client is x64 since 2019 (gmod_win64.exe) -- prefer x64
if exist "x64\Release\d1bridge_dll.dll" goto pick64
if exist "Release\d1bridge_dll.dll" goto pick32
echo [ERROR] No build output found
pause
exit /b 1

:pick64
copy /y "x64\Release\d1bridge_dll.dll" d1bridge.dll >nul
echo [OK] d1bridge.dll -- x64 build
goto install

:pick32
copy /y "Release\d1bridge_dll.dll" d1bridge.dll >nul
echo [OK] d1bridge.dll -- x86 build
goto install

:install
REM Сразу ставим в GMod, чтобы не расходились версии.
REM Если GMod запущен — файл залочен, копирование не удастся.
set "GMOD_DIR=D:\SteamLibrary\steamapps\common\GarrysMod"
if not exist "%GMOD_DIR%" goto done
if not exist "%GMOD_DIR%\garrysmod\lua\bin" goto done
copy /y "d1bridge.dll" "%GMOD_DIR%\garrysmod\lua\bin\gmcl_d1bridge_win64.dll" >nul 2>&1
if errorlevel 1 (
    echo [WARN] GMod запущен -- DLL залочена. Закрой GMod и запусти скрипт снова.
) else (
    echo [OK] Установлено в GMod: gmcl_d1bridge_win64.dll
)
goto done
goto done

:done
echo.
echo Now run: bridge\reader\d1bridge_install.bat
pause
exit /b 0

:no_msbuild
echo [ERROR] MSBuild or MSVC tools not found
pause
exit /b 1

:build_fail
echo.
echo [ERROR] Build failed
pause
exit /b 1

:make_def
REM %1 = dll, %2 = exports list, %3 = def file
powershell -NoProfile -Command "$d='%~1'; & '%DUMPBIN%' /exports $d | Select-String '^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+\S+' | ForEach-Object { ($_ -split '\s+')[-1] } | Where-Object { $_ -match '^(lua|luaL)_' } | Set-Content '%~2'"
echo LIBRARY lua_shared.dll> "%~3"
echo EXPORTS>> "%~3"
type "%~2" >> "%~3"
goto :eof
