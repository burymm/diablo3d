# 03. Устройство Diablo 1: The Hell 4 (TH4)

Источник: `vendor/the-hell-4-src` (HEAD `e8d0cc7`). Всё ниже — факты из исходников,
если явно не помечено как «предположение».

## Происхождение и природа

- Ядро — **Hellfire v1.01**, деобфусцированный через IDA (начато в 2007). Поверх — годы
  правок TH1→TH2→TH3→TH4. Часть кода осталась «decompilatus Diablii» (сырой код декомпилятора).
- Язык: **C++17**, платформа **Win32 (x86, 32-бит)**, сборка MSVC (`TheHell_4.sln`,
  платформа `Win32`, toolset v143 / VS Build Tools). Плюс есть CMake-файл, помеченный
  «clion project. Not to build».
- Известный состав: `src/*.cpp` (~126 файлов), сторонние библиотеки в `lib/`
  (Storm/MPQ, zlib, bzip2, pklib, zfs, huffman, ogg/vorbis, Smack для видео).
- Рендер: **Direct3D** (`dx.cpp`, `dx_utility.cpp`) + **HLSL-шейдеры** (`*.hlsl`:
  Bloom, Fog, Effects/PostProcess, Vignetting, PaletteShader, LineShader и т.д.).
  Есть fallback на DirectDraw.
- Ресурсы: архивы MPQ (`DIABDAT.MPQ`, `TH4data.mor`, `TH4loc_*.mor`) через **Storm**;
  часть кода Storm/`strm2.dll` тоже в репозитории (`Storm.cpp`, `storm_*.cpp`).
- Аудио: OGG/Vorbis, DirectSound.

## Архитектура загрузки (важно!)

- Исторически TH — это **загрузчик + игровая DLL**: `TH.exe` инжектит `HELL2.dll`
  (игровая логика) и `strm2.dll` (платформа/Storm). В `src/TH1dll.cpp` реализована
  вся машинерия загрузки/инъекции DLL (`LoadLibrary`, `GetProcAddress`, правка секций,
  ошибки `ER_dll_not_found`, `ER_cannot_inject_dll`), а `src/Hell.cpp` содержит `DllMain`.
- Современная сборка (по `BUILD.md`) выдаёт **`TH4.exe`** (Win32). То есть единый exe,
  но код DLL-загрузки в проекте сохранён.
- **Зацепка для интеграции:** модульность «загрузчик + DLL» означает, что теоретически
  можно подсунуть свою DLL рядом с игрой. Требует проверки (спайк), но это потенциально
  способ инструментировать игру без пересборки exe.

## Модель игрового мира (ядро для экспорта)

Мир — **изометрическая тайловая сетка**. Ключевое из `src/vars.h`, `src/common.h`,
`src/structs.h`, `src/enums.h`:

- **Fine Map**: `FineMap_112 = 112`. То есть основная «мелкая» карта — **112×112**.
  (`FineMap_112 = 2 * (Map_40 + MapDirty_16)`, где `Map_40 = 40`, `MapDirty_16 = 16`.)
- **Big Map**: `Map[40][40]` — «крупная» карта (оригинальный уровень); `FixedMap[40][40]` —
  её флаги; `AltMap[40][40]`.
- Основные массивы мира (все на 112×112, если не указано иное):

  | Массив | Тип | Смысл |
  |---|---|---|
  | `PlayerMap` | `char[112][112]` | проходимость/навигационная карта игрока |
  | `FlagMap` | `uchar[112][112]` | флаги клеток |
  | `ItemMap` | `uchar[112][112]` | предметы на земле |
  | `ObjectsMap` | `char[112][112]` | объекты (двери, бочки, алтари…) |
  | `MonsterMap` | `int[112][112]` | монстры |
  | `MissilesMap` | `MissileIndexT[112][112]` | снаряды |
  | `DeathMonstersMap` | `ushort[112][112]` | трупы монстров |
  | `BloodMap` | `uchar[112][112]` | кровь на полу |
  | `StaticLightMap`, `LightMap` | `uchar`/`char[112][112]` | статический/динамический свет |
  | `TransMap` | `uchar[112][112]` | прозрачность (стены у края видимости) |
  | `ArchGraphicsMap` | `char[112][112]` | графика архитектуры |

- **`TileMap[112*112]` (тип `TileColumn`)** — «cel-карта»: для каждой клетки — набор
  графических слоёв. `union TileColumn { TileID Layer[8]; ushort tile[16]; }` — до 8 слоёв.
  Это НАИЛУЧШИЙ источник для генерации 3D-геометрии клетки (см. `06-2d-v-3d.md`).
- Классификаторы клеток: `IsWall[2049]`, `TileBlockWalking[2049]`, `TileBlockSight[2049]`,
  `TileBlockMissle[2049]`, `WallsTransparency[2049]` — по типу тайла определяют, стена ли
  это, блокирует ли ход/обзор/снаряды. Идеально для построения коллизий и стен в 3D.

## Сущности

- **`struct Player`** (`structs.h:543`): позиция `Row/Col` (мировые), `NextRow/NextCol`,
  `TargetRow/TargetCol`, `xOfs/yOfs` (дробное смещение внутри тайла), `xVel/yVel`,
  `dir/nextDir`, `CurAction`, `destAction`+параметры, анимация (frame/tick/count/delay),
  `CurrentSpellIndex`, `readySpellType`, класс `ClassID`/`fullClassId`, статы
  (`Cur*`/`Base*` Str/Mag/Dex/Vit), жизни/мана (`CurLife`/`MaxCurLife`, `CurMana`),
  `CharLevel`, `Xp`, `TotalGold`, куча флагов (running, attacking, lvlChanging…).
- **`struct Monster`** (`structs.h:919`): `SpriteIndex`, `CurAction`, `goal`, `Row/Col`,
  `NextRow/Col`, `prevRow/Col`, `DeltaX/Y`, `SpeedX/Y`, `Orientation`, `TargetIndex`,
  `TargetRow/Col`, `curAnimation`, кадры анимации, `BaseLife`/`CurrentLife`, `ai` (индекс
  функции ИИ), `intel`, `flag`, `BossID`/`newBossId`, `acidDot` (яд) и т.д.
- **`struct Object`** (`structs.h:1635`), **`struct Item`** (`structs.h:190`),
  **`struct Missile`** (`structs.h:1978`), **`struct Portal`** (`structs.h:1589`),
  **`struct TileColumn`** (`structs.h:1552`).
- Данные типов (базы) — в `BaseMonster.cpp`, `BaseItems.cpp`, `UniqueItems.cpp`,
  `UniqueMonsters.cpp`, `UniqueSets.cpp`, `Affixes*.cpp`, `Spells.cpp`, `Perks*.cpp`,
  `BaseObjectsOnMap.cpp`, `BaseQuests.cpp`, `SynergyData.cpp`, `Traits.cpp`.

## Геометрия экрана (изометрия)

- Из `automap.cpp`: шаг по оси X — **32 px**, по оси Y — **16 px** (`AutomapZoom32 = 32`,
  `AutomapZoom16 = 16`). Это классическая **изометрия 2:1** (ромб тайла 64×32 на экране).
- Позиция героя на карте — `PlayerRowPos`, `PlayerColPos`.
- ⚠️ Точную формулу «мир → экран» (в `Draw.cpp`/`Engine.cpp`) нужно подтвердить перед
  реализацией маппинга. Помечено как задача в `09-roadmap.md`.

## Готовый «снимок мира» (важная находка)

- **`struct DungeonInfo`** (`src/game.h`) агрегирует в один блок всё состояние подземелья:
  `Player`, `LastPlayerInfo`, `PlayerMap`, `MagicItemsStoreArray`, `Items`, `ItemMap`,
  `ItemAvailable/Active`, `Missiles`, `MissilesMap`, `MissileIndexes`,
  `DungeonRandSeed`, `Portals`, `TotalSlain`, `LightIndexes`, `LightMap`, `StaticLightMap`,
  `VisionList`, `Objects`, `ObjectsMap`, `ObjectActive/Available`, `Monsters`,
  `MonsterIndexes`, `MonsterMap`, `DeathMonstersMap`, `FlagMap`, `AutoMap`, `BloodMap`.
- Это то, что игра **уже сериализует в сейв** (`SaveBuffer_Dungeon`, `CodeSave.cpp`,
  `Saving.cpp`, `MpqSave.cpp`, `serialize.cpp`). Сейвы лежат в `th4_save_sp/*.ssv`.
- **Вывод:** у TH4 уже есть механизм «выгрузить весь мир в буфер». Экспорт в мост можно
  строить на той же модели состояния, не изобретая её с нуля.

## Сетевой слой (для сведения)

- Файлы: `Net.cpp`, `multi.cpp`, `multi.h`, `sync.cpp/.h`, `tmsg.cpp/.h`, `msg.cpp/.h`,
  `Server.cpp`, `Server.h`, `Server/Server.vNext.vcxproj`.
- Модель сети — **оригинальная Diablo**: turn-based синхронизация
  (`SNetSendTurn`), а не современный поток снимков состояния. Пакеты, размеры очереди,
  `MaxCountOfPlayersInGame` (1 = single player), `NetPlayerCount`.
- **Вывод:** сетевой протокол игры — не то, что стоит «переиспользовать» как API моста
  (он низкоуровневый и привязан к модели ходов). Проще сделать свой экспорт поверх
  глобального состояния.
- Наличие отдельного таргета `Server` намекает на существующий серверный/without-GUI путь —
  стоит изучить ближе (задача в `09-roadmap.md`).

## Сборка (как есть)

- `InitProject.bat` → создаёт `personal.props` и `thehell4.vcxproj.user`.
- В `personal.props`: `GameFolder` (куда класть `TH4.exe`, путь с `\` на конце) и
  `FxCopDir` (папка с `fxc.exe` из Windows SDK для компиляции HLSL).
- Сборка: `MSBuild TheHell_4.sln /p:Configuration=Release /p:Platform=Win32` или `build.ps1`.
- ⚠️ **Критический спайк:** проверить, что форк вообще собирается в текущем окружении и
  что собранный `TH4.exe` запускает нашу игру (та же версия данных). Только после этого
  становится реальным «Вариант A» (экспорт в исходниках).

## Инвентарь форматов/ресурсов (справочно)

- **MPQ** — архивы Blizzard/Storm (`DIABDAT.MPQ`, `TH4data.mor`): спрайты CEL/CL2, уровни,
  палитры, звук, таблицы.
- **CEL / CL2** — спрайтовые тайлы и анимации (8 направлений у монстров).
- **`.ssv`** — сейвы персонажа/подземелья (см. `DungeonInfo`).
- **`.dun` / `.min`** — данные уровней (например `res/thdata/Levels/L0Data/Ravenholm.dun`).
- **`.trn`** — палитровые трансляции (перекраска спрайтов/монстров).
