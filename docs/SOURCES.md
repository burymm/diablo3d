# Источники и где что лежит

## Внешние

- Репозиторий исходников TH4: https://github.com/roboserg/the-hell-4-src
  (форк деобфусцированного Hellfire v1.01; README с разрешениями автора).
- Discord The Hell (для вопросов по моддингу): https://discord.gg/AN9NukZFbN
- Сайт мода: https://www.patreon.com/thmod

## Локально (зафиксировано)

| Что | Путь |
|---|---|
| Игра TH4 | `e:\games\The Hell IV` |
| Garry's Mod | `d:\SteamLibrary\steamapps\common\GarrysMod` |
| Проект | `e:\games\diablo-1-source` |
| Исходники TH4 (клон) | `e:\games\diablo-1-source\vendor\the-hell-4-src` |

## Ключевые файлы в исходниках TH4 (карта для навигации)

- `README.md`, `BUILD.md`, `InitProject.bat`, `TheHell_4.sln`, `CMakeLists.txt` — сборка.
- `src/structs.h` — сущности: `Player` (543), `Monster` (919), `Object` (1635),
  `Item` (190), `Missile` (1978), `TileColumn` (1552), `Portal` (1589).
- `src/vars.h` — глобальные массивы мира (`PlayerMap`, `MonsterMap`, `TileMap`,
  `FlagMap`, `LightMap`, `ObjectsMap`, `MissilesMap` и др.).
- `src/game.h` — `DungeonInfo` (агрегат состояния для сейва).
- `src/common.h`, `src/enums.h` — `FineMap_112`, `Map_40`, ограничения координат.
- `src/GenerateMap.cpp`, `src/Room.cpp`, `src/Halls.cpp`, `src/GenerateQuestFloor.cpp` —
  генерация уровней.
- `src/Player.cpp`, `src/Monster.cpp`, `src/Object.cpp`, `src/Item.cpp`, `src/Missile.cpp`,
  `src/Path.cpp` — логика сущностей.
- `src/Draw.cpp`, `src/Engine.cpp`, `src/automap.cpp`, `src/dx.cpp`, `*.hlsl` — рендер и
  геометрия экрана (изометрия).
- `src/Net.cpp`, `src/multi.cpp`, `src/sync.cpp`, `src/tmsg.cpp`, `src/Server.cpp`,
  `Server/Server.vNext.vcxproj` — сеть/сервер.
- `src/TH1dll.cpp`, `src/Hell.cpp` (`DllMain`) — загрузка/инъекция DLL, `HELL2.dll`.
- `src/Saving.cpp`, `src/CodeSave.cpp`, `src/MpqSave.cpp`, `src/serialize.cpp` — сохранения.
- `lib/txt/*` — заметки по реверсу: указатели, адреса данных, функции, списки монстров,
  уникальные предметы и т.д. (`__POINTERS.txt`, `__DATA ADDRESSES.txt`, `_FUNCTIONS.txt`, …).
- `doc/DevNotes.txt`, `doc/Todo_List.txt`, `doc/Coliseum.txt` — заметки разработчиков.
- `res/thdata/...` — примеры ресурсов.

## Ключевые места в установке GMod

- `garrysmod/lua/` — Lua (`autorun`, `entities`, `weapons`, `includes`…).
- `garrysmod/lua/includes/modules/` — доступные модули (`http`, `file`, `net`, `sql`…).
- `garrysmod/lua/bin/` — нативные Lua-модули (по умолчанию отсутствует).
- `garrysmod/gamemodes/` — `base`, `sandbox`, `terrortown`.
- `garrysmod/addons/` — аддоны (создаётся).
- `garrysmod/data/` — песочница файлового доступа (`file.Read/Write`, путь `DATA`).
- `garrysmod/steam.inf`, `garrysmod/garrysmod.ver` — версии (prerelease, 2026.04.29).

## Как обновлять клон исходников

```
cd e:\games\diablo-1-source\vendor\the-hell-4-src
git pull
```
(Клон сделан `--depth 1`; при необходимости истории — `git fetch --unshallow`.)

## Зафиксированное состояние на момент создания документов

- Установленная игра: **TH4 alpha 0.772** (`e:\games\The Hell IV`).
- Клон TH4: HEAD `e8d0cc7468fe93227956d7477c7735e07a831c7f` («chore: update gitignore»).
- GMod: `PatchVersion=2026.04.29`, `garrysmod.ver = 260917 1920`, канал prerelease,
  присутствует `gmod_win64.exe`.
