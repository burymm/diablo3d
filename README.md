# diablo3d — Diablo 1: The Hell 4 in 3D (Garry's Mod)

<!-- ==================================================================== -->
<!--  ENGLISH                                                             -->
<!-- ==================================================================== -->

**Goal:** play **Diablo 1: The Hell 4 (TH4)** in **3D** inside **Garry's Mod (GMod)** —
shooter-style, like Heretic/Hexen, but on **hardcore** and on TH4's **randomly
generated** dungeon levels.

**Status (2026-10-21):** the bridge works **in both directions, directly through
shared memory**:

- **TH4 → GMod:** `th43d.exe` publishes the hero state and the level map into the
  named shared memory `D1BridgeState` → a binary GMod Lua module
  (`gmcl_d1bridge_win64.dll`) reads it → the addon draws the HUD.
  **No intermediate files, no Python bridge.**
- **GMod → TH4:** a command goes through `send_command` in the DLL → shared memory →
  `Player.walkPath` inside TH4 (the native path: `MakePlayerPath` → `FindPath`).
  The game handles the movement itself — **no clicks and no input latency**.
- Read: HP / mana / gold / XP / level / position / facing + the level map
  (`FineMap`, `TileBlockWalking`, `PlayerMap`).
- **Measured input latency: 54–110 ms** (the old click-based fallback was
  209–454 ms). All 8 walk directions verified in the live game.
- **3D view of the level** is implemented (`bridge/gmod/d1scene.lua`): the real
  TH4 map data, rendered with GMod's immediate-mode mesh API, ~3300 quads at
  ~1.7 ms per frame.
- Next: server-side rendering, monsters in 3D, shooting (attack command),
  HUD.

## The idea in one paragraph

Play **Diablo 1: The Hell 4 (TH4)** in **3D** inside **Garry's Mod (GMod)**.
For that a "bridge" is built that translates the game world state from TH4 into
GMod and sends player commands (movement, attack, cast, …) back. TH4 remains the
**authoritative** source of game logic; GMod is the 3D presentation (rendering +
input). In the long run the bridge should become a **universal API**, so that
Diablo 1 data can be consumed by any other engine, not only GMod.

## Key facts that shaped the approach

1. **TH4 sources are open** — a deobfuscated Hellfire v1.01 fork (C++),
   repository `roboserg/the-hell-4-src`. The author's licence: "do whatever you
   want, just name the derivative work differently and keep the README". This
   allows **embedding the state export directly into the game** instead of
   reading someone else's process from the outside.
2. **GMod is fully extensible**: Lua (client + server), a rich renderer,
   entities, binary Lua modules (DLLs) and external IPC. That makes it a good
   platform for the 3D presentation.
3. The hard part is **neither networking nor logic**, but **translating
   Diablo's 2D isometric view into 3D** (Diablo 1 has no 3D geometry at all —
   levels are pre-rendered 2D tiles).

## Repository layout

```
diablo3d/
├─ README.md                 ← you are here
├─ AGENT.md                  ← rules for AI agents working on this repo
├─ .gitmodules               ← TH4 sources as a submodule
├─ docs/                     ← knowledge base (read in order)
│  ├─ 00-resheniya.md        ← decision log (read first)
│  ├─ 01-ideya-i-celi.md     ← goals and principles
│  ├─ 02-arhitektura.md      ← architecture options and recommendation
│  ├─ 03-th4-ustroystvo.md   ← how TH4 works internally
│  ├─ 04-gmod-ustroystvo.md  ← how GMod works internally
│  ├─ 05-most-i-api.md       ← bridging techniques
│  ├─ 06-2d-v-3d.md          ← 2D → 3D problems
│  ├─ 07-riski-i-yuridika.md ← legal risks
│  ├─ 08-otkrytye-voprosy.md ← open questions
│  ├─ 09-roadmap.md          ← roadmap
│  ├─ 10-mvp-spike.md        ← the first practical step (closed)
│  ├─ 11-upravlenie-i-kamera.md ← controls and camera
│  ├─ 12-ocenka-slozhnosti.md  ← complexity estimate
│  ├─ 13-karta-pamyati-th4.md  ← TH4 memory map (reverse engineering)
│  ├─ 14-gmod-ad-don.md      ← the GMod addon
│  ├─ 15-obratnyy-kanal.md   ← the reverse channel: clicks, latency, limits
│  ├─ 16-agent-context.md    ← full project context for an agent
│  ├─ 17-gmod-api-ogranicheniya.md ← what works / doesn't in this GMod build
│  ├─ 18-geometriya-izometrii-th4.md ← exact TH4 isometric maths
│  ├─ 19-plan-3d-shooter.md  ← step-by-step plan to "play Diablo in 3D"
│  ├─ GLOSSARY.md
│  └─ SOURCES.md
├─ bridge/                   ← working code
│  ├─ gmod/                  ← GMod side (client + server)
│  │  ├─ d1bridge.lua        ← addon source (installed by the installer)
│  │  ├─ d1bridge_dll.cpp    ← binary GMod Lua module: shared memory reader
│  │  ├─ lua.hpp             ← Lua 5.1 headers (opaque lua_State)
│  │  ├─ d1control.lua       ← FPS controls: camera + WASD relative to camera
│  │  ├─ d1scene.lua         ← 3D level scene (IMesh + cam.Start3D)
│  │  ├─ d1iso.lua           ← 2D isometric fallback (orthographic projection)
│  │  ├─ d1*probe*.lua       ← API probes for GMod (see docs/17)
│  │  ├─ build_d1bridge_dll.bat ← module build (x86 + x64)
│  │  └─ d1bridge_dll.vcxproj
│  ├─ th4-patches/           ← our changes inside the TH4 sources
│  │  ├─ 0001-th4-shm-bridge.patch ← SHM publisher, export tool, project files
│  │  ├─ apply_patches.bat   ← applies the patch to the submodule
│  │  └─ README.md
│  └─ reader/                ← Python tooling (debugging, install)
│     ├─ d1shm_reader.py     ← read D1BridgeState from Python
│     ├─ d1shm_cmd.py        ← write commands into D1BridgeState
│     ├─ d1shm_latency2.py   ← latency measurement (t_accept / t_land)
│     ├─ d1reader.py         ← older reader (external memory access)
│     ├─ offsets.json        ← working field map (build 0.772)
│     ├─ luacheck.py         ← Lua syntax checker (no interpreter needed)
│     ├─ d1bridge_install.bat← install addon + DLL into GMod
│     └─ *.py                ← diagnostics (diffheap, findpos, …)
└─ vendor/
   └─ the-hell-4-src/        ← git-submodule: roboserg/the-hell-4-src
```

### Cloning

```bash
git clone --recurse-submodules https://github.com/burymm/diablo3d.git
# without the flag:
git submodule update --init
```

The TH4 sources are **not** committed here — they are a submodule
(`vendor/the-hell-4-src` → https://github.com/roboserg/the-hell-4-src.git,
pinned at commit `e8d0cc7`).

Our changes *inside* the TH4 sources (the shared-memory publisher) are kept as a
patch in `bridge/th4-patches/` and applied on top of the pristine submodule:

```bash
bridge\th4-patches\apply_patches.bat
```

### Building and installing

```bash
# 1. Build the GMod Lua module (GMod must be CLOSED — the file is locked)
cd bridge/gmod
build_d1bridge_dll.bat

# 2. Install the addon + DLL into GMod
cd ../reader
d1bridge_install.bat

# 3. Apply our TH4 patch and rebuild th43d.exe
cd ../../bridge/th4-patches
apply_patches.bat
cd ../reader
build_th43d.bat
```

The DLL is installed as `garrysmod/lua/bin/gmcl_d1bridge_win64.dll` (client) and
`sv_d1bridge_win64.dll` (server) — the standard format for binary GMod modules
(see `docs/00-resheniya.md`, Р-30).

### 3D scene and FPS controls

```bash
# In the GMod console
lua_openscript_cl "autorun/client/d1control.lua"   # controls: WASD relative to camera
lua_openscript_cl "autorun/client/d1scene.lua"     # 3D level scene
```

| Command | Action |
|---|---|
| `d1_debugshow` | HUD panel with input state |
| `d1_verbose` | Verbose chat output |
| `d1_look` | Current camera angles |
| `d1_reset` | Reset the view to the TH4 base angle |
| `d1scene_info` | Map data (area, walls, hero position) |
| `d1scene_cam [h] [back]` | Camera height and distance |
| `d1scene_cammode player\|iso` | First-person view / TH4 isometric view |
| `d1scene_fov [f]` | Field of view |
| `d1scene_scale [m]` | World scale |

**Important:** the GMod world is **Z-up** (X=east, Y=north, Z=up).
The horizontal plane is XY — read `f.x`/`f.y`, **not** `f.z`.

### Environment (fixed paths)

| What | Where |
|---|---|
| TH4 (installed game) | `e:\games\The Hell IV` — **DO NOT TOUCH (saves/language)** |
| Test copy | `e:\games\TheHell3D` (built `th43d.exe`) |
| Garry's Mod | `d:\SteamLibrary\steamapps\common\GarrysMod\` (x64 client) |
| Project | `e:\games\diablo-1-source\` |
| TH4 sources | `vendor/the-hell-4-src/` (submodule, `e8d0cc7`) |

### Where to start reading

1. `docs/16-agent-context.md` — full project context.
2. `docs/00-resheniya.md` — the decision log: how the bridge works and why.
3. `docs/19-plan-3d-shooter.md` — the current goal and the step-by-step plan.
4. `docs/17-gmod-api-ogranicheniya.md` — what works / doesn't in this GMod build
   (read before writing rendering code).
5. `docs/18-geometriya-izometrii-th4.md` — the exact TH4 isometric maths.

---

<!-- ==================================================================== -->
<!--  РУССКИЙ                                                              -->
<!-- ==================================================================== -->

# diablo3d — Diablo 1: The Hell 4 в 3D (Garry's Mod)

**Цель:** играть в **Diablo 1: The Hell 4 (TH4)** в **3D** внутри **Garry's Mod
(GMod)** — в стиле шутера (как Heretic/Hexen), но на **хардкоре** и на
**рандомных** подземельях TH4.

**Статус (на 21.10.2026):** мост работает **в обе стороны, напрямую через
разделяемую память**:

- **TH4 → GMod:** `th43d.exe` публикует состояние героя и карту уровня в
  именованную разделяемую память `D1BridgeState` → бинарный Lua-модуль GMod
  (`gmcl_d1bridge_win64.dll`) читает её → аддон рисует HUD.
  **Никаких промежуточных файлов и никакого Python-моста.**
- **GMod → TH4:** команда → `send_command` в DLL → разделяемая память →
  `Player.walkPath` внутри TH4 (нативный путь: `MakePlayerPath` → `FindPath`).
  Движение обрабатывает сама игра — **без кликов и без задержки ввода**.
- Читаются HP/мана/золото/опыт/уровень/координаты/направление + карта уровня
  (`FineMap`, `TileBlockWalking`, `PlayerMap`).
- **Задержка ввода: 54–110 мс** (старый клик-фолбэк был 209–454 мс).
  Все 8 направлений ходьбы проверены в живой игре.
- **3D-вид уровня реализован** (`bridge/gmod/d1scene.lua`): настоящие данные
  карты TH4, отрисовка immediate-mode мешами GMod, ~3300 квадов за ~1.7 мс.
- Дальше: отрисовка на сервере, монстры в 3D, стрельба (команда атаки), HUD.

## Идея в одном абзаце

Играть в **Diablo 1: The Hell 4 (TH4)** в **3D** внутри **Garry's Mod (GMod)**.
Для этого строится «прослойка» (мост), которая транслирует состояние игрового
мира из TH4 в GMod, а обратно отправляет команды игрока (движение, атака, каст
и т.д.). TH4 остаётся **авторитетным** источником игровой логики, GMod — это
3D-представление (рендер + управление). В перспективе мост должен стать
**универсальным API**, чтобы данные из Diablo 1 можно было брать в любой другой
движок/игру, а не только в GMod.

## Ключевые факты, определившие подход

1. **Исходники TH4 открыты** — форк деобфусцированного Hellfire v1.01 (C++),
   репозиторий `roboserg/the-hell-4-src`. Лицензия автора: «делай что хочешь,
   только назови производную работу по-другому и сохрани README». Это даёт
   возможность **встроить экспорт состояния прямо в игру**, а не читать чужой
   процесс снаружи.
2. **GMod полностью расширяем**: Lua (клиент + сервер), богатый рендер,
   сущности, бинарные Lua-модули (DLL) и внешний IPC. Это даёт площадку для
   3D-представления.
3. Главная сложность — **не сеть и не логика**, а **перевод 2D-изометрии Diablo
   в 3D** (в Diablo 1 нет 3D-геометрии вообще; уровни — это заранее
   отрисованные 2D-тайлы).

## Структура репозитория

```
diablo3d/
├─ README.md                 ← вы здесь
├─ AGENT.md                  ← правила для AI-агентов, работающих с репозиторием
├─ .gitmodules               ← исходники TH4 как submodule
├─ docs/                     ← база знаний (читать по порядку)
│  ├─ 00-resheniya.md        ← журнал принятых решений (читать первым)
│  ├─ 01-ideya-i-celi.md     ← цели и принципы
│  ├─ 02-arhitektura.md      ← варианты архитектуры и рекомендация
│  ├─ 03-th4-ustroystvo.md   ← как устроен TH4 внутри
│  ├─ 04-gmod-ustroystvo.md  ← как устроен GMod внутри
│  ├─ 05-most-i-api.md       ← техники мостирования
│  ├─ 06-2d-v-3d.md          ← проблемы 2D → 3D
│  ├─ 07-riski-i-yuridika.md ← юридические риски
│  ├─ 08-otkrytye-voprosy.md ← открытые вопросы
│  ├─ 09-roadmap.md          ← дорожная карта
│  ├─ 10-mvp-spike.md        ← первый практический шаг (закрыт)
│  ├─ 11-upravlenie-i-kamera.md ← управление и камера
│  ├─ 12-ocenka-slozhnosti.md  ← оценка сложности
│  ├─ 13-karta-pamyati-th4.md  ← карта памяти TH4 (реверс)
│  ├─ 14-gmod-ad-don.md      ← аддон GMod
│  ├─ 15-obratnyy-kanal.md   ← обратный канал: клики, задержка, ограничения
│  ├─ 16-agent-context.md    ← полный контекст проекта для агента
│  ├─ 17-gmod-api-ogranicheniya.md ← что работает/не работает в этой сборке GMod
│  ├─ 18-geometriya-izometrii-th4.md ← точная математика изометрии TH4
│  ├─ 19-plan-3d-shooter.md  ← план по шагам до «поиграть в Diablo в 3D»
│  ├─ GLOSSARY.md
│  └─ SOURCES.md
├─ bridge/                   ← рабочий код
│  ├─ gmod/                  ← сторона GMod (клиент + сервер)
│  │  ├─ d1bridge.lua        ← исходник аддона (ставится установщиком)
│  │  ├─ d1bridge_dll.cpp    ← бинарный Lua-модуль GMod: чтение разделяемой памяти
│  │  ├─ lua.hpp             ← заголовки Lua 5.1 (непрозрачный lua_State)
│  │  ├─ d1control.lua       ← FPS-управление: камера + WASD относительно камеры
│  │  ├─ d1scene.lua         ← 3D-сцена уровня (IMesh + cam.Start3D)
│  │  ├─ d1iso.lua           ← 2D-изометрия (ортографическая проекция), запасной путь
│  │  ├─ d1*probe*.lua       ← зонды по API GMod (см. docs/17)
│  │  ├─ build_d1bridge_dll.bat ← сборка модуля (x86 + x64)
│  │  └─ d1bridge_dll.vcxproj
│  ├─ th4-patches/           ← наши правки внутри исходников TH4
│  │  ├─ 0001-th4-shm-bridge.patch ← публикатор SHM, экспорт адресов, файлы проекта
│  │  ├─ apply_patches.bat   ← применение патча к submodule
│  │  └─ README.md
│  └─ reader/                ← Python-инструменты (отладка, установка)
│     ├─ d1shm_reader.py     ← чтение D1BridgeState из Python
│     ├─ d1shm_cmd.py        ← запись команд в D1BridgeState
│     ├─ d1shm_latency2.py   ← замер задержки (t_accept / t_land)
│     ├─ d1reader.py         ← старый reader (внешнее чтение памяти TH4)
│     ├─ offsets.json        ← рабочая карта полей (сборка 0.772)
│     ├─ luacheck.py         ← проверка Lua без интерпретатора
│     ├─ d1bridge_install.bat← установка аддона + DLL в GMod
│     └─ *.py                ← диагностика (diffheap, findpos, ...)
└─ vendor/
   └─ the-hell-4-src/        ← git-submodule: roboserg/the-hell-4-src
```

### Клонирование

```bash
git clone --recurse-submodules https://github.com/burymm/diablo3d.git
# без флага --recurse-submodules:
git submodule update --init
```

Исходники TH4 в репозиторий **не входят** — они подключены как submodule
(`vendor/the-hell-4-src` → https://github.com/roboserg/the-hell-4-src.git,
зафиксирован коммит `e8d0cc7`).

Наши изменения *внутри* исходников TH4 (публикация состояния в разделяемую
память) хранятся патчем в `bridge/th4-patches/` и применяются поверх чистого
submodule:

```bash
bridge\th4-patches\apply_patches.bat
```

### Сборка и установка

```bash
# 1. Сборка Lua-модуля GMod (GMod должен быть ЗАКРЫТ — файл блокируется!)
cd bridge/gmod
build_d1bridge_dll.bat

# 2. Установка аддона + DLL в GMod
cd ../reader
d1bridge_install.bat

# 3. Применение патча к TH4 и пересборка th43d.exe
cd ../th4-patches
apply_patches.bat
cd ../reader
build_th43d.bat
```

DLL ставится как `garrysmod/lua/bin/gmcl_d1bridge_win64.dll` (клиент) и
`sv_d1bridge_win64.dll` (сервер) — это штатный формат бинарных модулей GMod
(подробности — `docs/00-resheniya.md`, Р-30).

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
| `d1_reset` | Сброс обзора к базовому ракурсу TH4 |
| `d1scene_info` | Данные карты (область, стены, позиция героя) |
| `d1scene_cam [h] [back]` | Высота и расстояние камеры |
| `d1scene_cammode player\|iso` | Вид от первого лица / изометрия TH4 |
| `d1scene_fov [f]` | Поле зрения |
| `d1scene_scale [m]` | Масштаб мира |

**Важно:** в GMod мир **Z-up** (X=восток, Y=север, Z=вверх).
Горизонтальная плоскость — XY, читать `f.x`/`f.y`, **не** `f.z`.

### Окружение (зафиксировано)

| Что | Где |
|---|---|
| TH4 (установленная игра) | `e:\games\The Hell IV` — **НЕ ТРОГАТЬ (сейвы/язык)** |
| Копия для тестов | `e:\games\TheHell3D` (собираемый `th43d.exe`) |
| Garry's Mod | `d:\SteamLibrary\steamapps\common\GarrysMod\` (клиент x64) |
| Проект (этот репозиторий) | `e:\games\diablo-1-source\` |
| Исходники TH4 | `vendor/the-hell-4-src/` (submodule, `e8d0cc7`) |

### Быстрый старт чтения

1. `docs/16-agent-context.md` — полный контекст проекта (читать первым).
2. `docs/00-resheniya.md` — журнал решений: как устроен текущий мост.
3. `docs/19-plan-3d-shooter.md` — **текущая цель** и план по шагам.
4. `docs/17-gmod-api-ogranicheniya.md` — **ограничения API GMod в этой
   сборке**: что работает, что нет (читать перед кодом рендера).
5. `docs/18-geometriya-izometrii-th4.md` — точная математика изометрии TH4.
6. `docs/01-ideya-i-celi.md` — что именно мы хотим получить.
7. `docs/02-arhitektura.md` — варианты построения системы (и рекомендация).
8. `docs/08-otkrytye-voprosy.md` — вопросы, которые нужно решить.
