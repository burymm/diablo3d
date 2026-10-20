@echo off
chcp 65001 >nul
cd /d "e:\games\TheHell3D"
echo Starting th43d.exe...
start "" "th43d.exe"
timeout /t 3 /nobreak >nul
if exist "d1map_export.txt" (
    echo Export file found:
    type "d1map_export.txt"
) else (
    echo Export file not found yet, wait...
    timeout /t 5 /nobreak >nul
    if exist "d1map_export.txt" (
        echo Export file found:
        type "d1map_export.txt"
    ) else (
        echo Export file still not found
    )
)
pause
