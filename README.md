# diablo-1-source — Diablo 1: The Hell 4 → 3D (Garry's Mod)

**Проект:** `diablo-1-source`
**Статус:** мост работает **в обе стороны, напрямую через разделяемую память**
(проверено 20.10.2026):
- **TH4 → GMod:** `th43d.exe` публикует состояние героя и карту в именованную
  разделяемую память `D1BridgeState` → бинарный Lua-модуль GMod
  `gmcl_d1bridge_win64.dll` читает её → аддон `d1bridge.lua` показывает HUD.
  **Никаких файлов и никакого Python-моста.**
- **GMod → TH4:** команда → `send_command` в DLL → shared memory →
  `Player.walkPath` в TH4 (нативный путь: `MakePlayerPath` → `FindPath`).
  Игра сама обрабатывает движение — **без кликов и без задержки ввода**.
- Читаются HP/мана/золото/опыт/уровень/координаты/направление + карта уровня
  (`FineMap`, `TileBlockWalking`, `PlayerMap`).
- Следующие шаги: 3D-сцена уровня (данные карты уже доступны), проверка
  нативного управления в живой игре, экспорт монстров/предметов.
**Цель этого репозитория:** собрать знания, договориться об архитектуре и зафиксировать план.

## Идея в одном абзаце

Играть в **Diablo 1: The Hell 4 (TH4)** в **3D** внутри **Garry's Mod (GMod)**.
Для этого строится «прослойка» (мост), которая транслирует состояние игрового мира из
TH4 в GMod, а обратно отправляет команды игрока (движение, атака, каст и т.д.).
TH4 остаётся **авторитетным** источником игровой логики, GMod — это 3D-представление
(рендер + управление). В перспективе мост должен стать **универсальным API**, чтобы данные
из Diablo 1 можно было брать в любой другой движок/игре, а не только в GMod.

## Ключевые факты, определившие подход

1. **Исходники TH4 открыты** — форк деобфусцированного Hellfire v1.01 (C++), репозиторий
   `roboserg/the-hell-4-src`. Лицензия автора: «делай что хочешь, только назови производную
   работу по-другому и сохрани README». Это даёт возможность **встроить экспорт состояния
   прямо в игру**, а не читать чужой процесс снаружи.
2. **GMod полностью расширяем**: Lua (клиент + сервер), богатый рендер, сущности,
   бинарные Lua-модули (DLL) и внешний IPC. Это даёт площадку для 3D-представления.
3. Главная сложность — **не сеть и не логика**, а **перевод 2D-изометрии Diablo в 3D**
   (в Diablo 1 нет 3D-геометрии вообще; уровни — это заранее отрисованные 2D-тайлы).

## Структура репозитория

```
diablo-1-source/
├─ README.md                 ← вы здесь
├─ docs/                     ← база знаний (читать по порядку)
│  ├─ 00-resheniya.md        ← журнал принятых решений (читать первым)
│  ├─ 01-ideya-i-celi.md
│  ├─ 02-arhitektura.md
│  ├─ 03-th4-ustroystvo.md
│  ├─ 04-gmod-ustroystvo.md
│  ├─ 05-most-i-api.md
│  ├─ 06-2d-v-3d.md
│  ├─ 07-riski-i-yuridika.md
│  ├─ 08-otkrytye-voprosy.md
│  ├─ 09-roadmap.md
│  ├─ 10-mvp-spike.md        ← первый практический шаг
│  ├─ 11-upravlenie-i-kamera.md
│  ├─ 12-ocenka-slozhnosti.md
│  ├─ 13-karta-pamyati-th4.md ← найденные смещения/адреса (реверс)
│  ├─ 14-gmod-ad-don.md        ← GMod-аддон (HUD поверх snapshot.json)
│  ├─ 15-obratnyy-kanal.md     ← обратный канал: клики, задержка, ограничения
│  ├─ 16-agent-context.md      ← контекст для агента (читать в первую очередь)
│  ├─ 17-gmod-api-ogranicheniya.md ← что работает/не работает в API GMod
│  ├─ 18-geometriya-izometrii-th4.md ← точная математика изометрии TH4
│  ├─ 19-plan-3d-shooter.md    ← план до «поиграть в Diablo в 3D»
│  ├─ GLOSSARY.md
│  └─ SOURCES.md
├─ vendor/
│  └─ the-hell-4-src/          ← git-submodule: roboserg/the-hell-4-src
├─ bridge/                   ← рабочий код моста
│  ├─ gmod/
│  │  ├─ d1bridge.lua        ← ИСХОДНИК аддона GMod (копируется установщиком)
│  │  ├─ d1bridge_dll.cpp    ← бинарный Lua-модуль GMod: чтение shared memory
│  │  ├─ lua.hpp             ← заголовки Lua 5.1 (непрозрачный lua_State)
│  │  ├─ build_d1bridge_dll.bat ← сборка модуля (x86 + x64)
│  │  └─ d1bridge_dll.vcxproj
│  └─ reader/                ← Python-инструменты (отладка, установка)
│     ├─ d1shm_reader.py     ← чтение D1BridgeState из Python (тест/отладка)
│     ├─ d1shm_cmd.py        ← запись команд в D1BridgeState из Python
│     ├─ d1shm_bridge.py     ← мост SHM -> snapshot.json (запасной путь)
│     ├─ d1shm_test.py       ← тест чтения shared memory
│     ├─ d1reader.py         ← старый reader (внешнее чтение памяти TH4)
│     ├─ offsets.json        ← рабочая карта полей (0.772)
│     ├─ luacheck.py         ← проверка Lua-аддона без интерпретатора
│     ├─ d1bridge_install.bat← установка аддона + DLL в GMod
│     └─ *.py                ← диагностика (diffheap, findpos, ...)
└─ vendor/
   └─ the-hell-4-src/        ← git-submodule: roboserg/the-hell-4-src (см. .gitmodules)
```

### Клонирование

```bash
git clone --recurse-submodules https://github.com/burymm/diablo3d.git
# без флага --recurse-submodules:
git submodule update --init
```

Исходники TH4 в репозиторий не входят — они подключены как submodule
(`vendor/the-hell-4-src` → https://github.com/roboserg/the-hell-4-src.git,
зафиксирован коммит `e8d0cc7`).

### Сборка и установка

```bash
# 1. Сборка Lua-модуля GMod (GMod должен быть ЗАКРЫТ — файл блокируется!)
cd e:\games\diablo-1-source\bridge\gmod
build_d1bridge_dll.bat

# 2. Установка аддона + DLL в GMod
cd ..\reader
d1bridge_install.bat

# 3. В GMod (консоль)
lua_openscript_cl "autorun/client/d1bridge.lua"
```

DLL устанавливается как `garrysmod/lua/bin/gmcl_d1bridge_win64.dll` —
это штатный формат бинарных модулей GMod (подробности — `docs/00-resheniya.md`, Р-30).

### 3D-сцена и FPS-управление

```bash
# В GMod (консоль)
lua_openscript_cl "autorun/client/d1control.lua"   # управление: WASD относительно камеры
lua_openscript_cl "autorun/client/d1scene.lua"     # 3D-сцена уровня
```

| Команда | Действие |
|---|---|
| `d1_debugshow` | HUD-панель состояния ввода |
| `d1_verbose` | Подробный вывод в чат |
| `d1_look` | Текущие углы камеры |
| `d1scene_info` | Данные карты (область, стены, позиция героя) |
| `d1scene_cam [h] [back]` | Высота и расстояние камеры |
| `d1scene_scale [m]` | Масштаб мира |

**Важно:** в GMod мир **Z-up** (X=восток, Y=север, Z=вверх).
Горизонтальная плоскость — XY, читать `f.x`/`f.y`, **не** `f.z`.

### Аддон GMod (исходник в репозитории)

```
e:\games\diablo-1-source\bridge\gmod\d1bridge.lua   ← правим ЭТОТ файл
D:\SteamLibrary\steamapps\common\GarrysMod\garrysmod\lua\autorun\client\d1bridge.lua   ← копия
```

## Окружение (зафиксировано)

| Что | Где |
|---|---|
| TH4 (установленная игра) | `e:\games\The Hell IV` — **НЕ ТРОГАТЬ (сейвы/язык)** |
| Копия для тестов | `e:\games\TheHell3D` (собираемый `th43d.exe`) |
| Garry's Mod | `d:\SteamLibrary\steamapps\common\GarrysMod\` (клиент x64) |
| Проект (этот репозиторий) | `e:\games\diablo-1-source\` |
| Исходники TH4 | `e:\games\diablo-1-source\vendor\the-hell-4-src\` (HEAD `e8d0cc7`) |

## Быстрый старт чтения

1. `docs/16-agent-context.md` — полный контекст проекта (читать первым).
2. `docs/00-resheniya.md` — журнал решений: как устроен текущий мост.
3. `docs/19-plan-3d-shooter.md` — **текущая цель**: «поиграть в Diablo в 3D»
   (шутер) и план по шагам.
4. `docs/17-gmod-api-ogranicheniya.md` — **ограничения API GMod в этой
   сборке**: что работает, что нет (читать перед кодом рендера).
5. `docs/18-geometriya-izometrii-th4.md` — точная математика изометрии TH4.
6. `docs/01-ideya-i-celi.md` — что именно мы хотим получить.
7. `docs/02-arhitektura.md` — варианты построения системы (и рекомендация).
8. `docs/08-otkrytye-voprosy.md` — вопросы, которые нужно решить.
