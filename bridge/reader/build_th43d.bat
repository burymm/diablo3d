@echo off
chcp 65001 >nul
cd /d "e:\games\diablo-1-source\vendor\the-hell-4-src"
echo Building th43d.exe...
"C:\Program Files\Microsoft Visual Studio\18\Community\MSBuild\Current\Bin\MSBuild.exe" TheHell_4.sln /p:Configuration=Release /p:Platform=Win32 /v:minimal
if %ERRORLEVEL% EQU 0 (
    echo Build OK
    copy /Y "e:\games\TheHell3D\th43d.exe" "e:\games\TheHell3D\th43d_backup.exe" >nul 2>&1
) else (
    echo Build FAILED
)
pause
