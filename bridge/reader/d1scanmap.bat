@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ============================================================
rem  d1scanmap.bat [ИмяГероя]
rem
rem  Перед сканом обновляет player_base_now в offsets.json через
rem  findhero (адреса в куче меняются при каждом запуске th43d.exe).
rem
rem  Имя можно не указывать — возьмётся из offsets.json (player_name).
rem  Если герой переименован/сменился — передай имя аргументом:
rem      d1scanmap.bat Kadgar
rem ============================================================

if "%~1"=="" (
    echo [*] Имя не указано — беру из offsets.json
    python findhero.py --apply
) else (
    echo [*] Ищу героя по имени: %~1
    python findhero.py --name "%~1" --apply
)
if errorlevel 1 (
    echo.
    echo [ERROR] findhero не смог найти героя.
    echo         Запусти игру ^(th43d.exe^), зайди в игру героем и повтори.
    pause
    exit /b 1
)

echo.
echo [*] Строю карту...
python scanmap.py
if errorlevel 1 (
    echo.
    echo [ERROR] scanmap завершился с ошибкой.
)
pause
