# AGENT.md

## Главное

**Все знания, прогресс, решения и документация — в папке `docs/`.**

Перед началом работы прочитай `docs/16-agent-context.md` — там полный контекст проекта.

## Правила

1. **Любой прогресс, новые найденные смещения, решения — сохраняй в `docs/`.**
   - Новые факты → `docs/00-resheniya.md` (журнал решений)
   - Новые смещения/адреса → `docs/13-karta-pamyati-th4.md`
   - Новые эксперименты → отдельный файл в `docs/` с описанием метода и результата

2. **Не потеряй то, что уже найдено.** Если что-то меняешь — добавляй, а не перезаписывай.

3. **Структура docs:**
   ```
   docs/
   ├─ 00-resheniya.md          ← журнал принятых решений (читать первым)
   ├─ 01..08                   ← концепция, архитектура, риски
   ├─ 09-roadmap.md            ← дорожная карта
   ├─ 10-mvp-spike.md          ← MVP (закрыт)
   ├─ 11-upravlenie-i-kamera.md ← управление и камера
   ├─ 12-ocenka-slozhnosti.md  ← оценка сложности
   ├─ 13-karta-pamyati-th4.md  ← карта памяти TH4
   ├─ 14-gmod-ad-don.md        ← GMod-аддон
   ├─ 15-obratnyy-kanal.md     ← обратный канал
   ├─ 16-agent-context.md      ← контекст для агента (читать в первую очередь)
   ├─ 17-gmod-api-ogranicheniya.md ← что работает/не работает в API GMod
   ├─ 18-geometriya-izometrii-th4.md ← точная математика изометрии TH4
   ├─ 19-plan-3d-shooter.md    ← план до «поиграть в Diablo в 3D»
   ├─ GLOSSARY.md              ← термины
   └─ SOURCES.md               ← источники
   ```

4. **Код — в `bridge/`, знания — в `docs/`.** Не смешивай.

5. **Текущий статус:** мост работает в обе стороны **напрямую через разделяемую
   память** (Р-25…Р-30). GMod читает `D1BridgeState` бинарным Lua-модулем
   `gmcl_d1bridge_win64.dll` — без файлов и без Python-моста.
   Серверная копия модуля `sv_d1bridge_win64.dll` тоже установлена (сервер
   читает SHM напрямую).
   **Цель (переформулирована 20.10.2026):** «поиграть в Diablo в 3D», стрельба
   как в Heretic/Hexen, на хардкоре и рандомных уровнях; TH4 остаётся
   источником правды. План — `docs/19-plan-3d-shooter.md`.
   **Перед кодом рендера обязательно прочитать `docs/17-gmod-api-ogranicheniya.md`**
   (у этой сборки GMod клиентский API сильно урезан).

## Исходники TH4 — git-submodule

```bash
git clone --recurse-submodules https://github.com/burymm/diablo3d.git
# или после обычного clone:
git submodule update --init
```
Модуль: `vendor/the-hell-4-src` → https://github.com/roboserg/the-hell-4-src.git
(зафиксирован коммит `e8d0cc7`). Сам vendor в репозиторий не коммитится.


## Сборка и установка

```bash
# Сборка DLL-модуля GMod (GMod должен быть закрыт — файл блокируется)
cd bridge\gmod
build_d1bridge_dll.bat

# Установка аддона + DLL
cd ..\reader
d1bridge_install.bat
```

## Окружение

| Что | Где |
|---|---|
| TH4 (установленная игра) | `e:\games\The Hell IV` — **НЕ ТРОГАТЬ (сейвы/язык)** |
| Копия для тестов | `e:\games\TheHell3D` (собираемый `th43d.exe`) |
| Garry's Mod | `d:\SteamLibrary\steamapps\common\GarrysMod\` |
| Проект | `e:\games\diablo-1-source\` |
| Исходники TH4 | `e:\games\diablo-1-source\vendor\the-hell-4-src\` (git-submodule) |
| Рабочий код моста | `bridge\gmod\d1bridge_dll.cpp`, `bridge\gmod\d1bridge.lua` |
| Рендер сцены | `bridge\gmod\d1scene.lua` (IMesh), `bridge\gmod\d1control.lua` (управление) |
