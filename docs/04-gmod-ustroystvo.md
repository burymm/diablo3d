# 04. Устройство Garry's Mod (GMod)

Источник: осмотр установки `d:\SteamLibrary\steamapps\common\GarrysMod`.

## Версия и платформа

- Движок: Source (ветка 2013). Версия клиента помечена как **prerelease**,
  `PatchVersion=2026.04.29` (`garrysmod/steam.inf`), `garrysmod.ver = 260917 1920`.
- Есть **64-битный** запуск (`gmod_win64.exe`) и 32-битный (`gmod.exe`).
- Структура: `bin/`, `garrysmod/` (игровые ресурсы + Lua), `platform/`, `sourceengine/`.

## Lua: точки расширения

- `garrysmod/lua/` — корень Lua: `autorun/`, `entities/`, `weapons/`, `derma/`,
  `vgui/`, `includes/`, `menu/`, `postprocess/`, `matproxy/`, `drive/`, `skins/`.
- `garrysmod/gamemodes/` — режимы: `base`, `sandbox`, `terrortown`.
  Гейммод = папка с `gamemode/*.lua` (клиент/сервер/shard) + `base.txt`.
- `garrysmod/addons/<имя>/` — папка аддонов (по умолчанию отсутствует, создаётся).
  Именно сюда логично класть наш аддон.
- **Два Lua-состояния:** клиент и сервер (файлы `cl_*.lua` / `sh_*.lua` / `sv_*.lua`).

## Доступные библиотеки Lua (важно для выбора транспорта)

Из `garrysmod/lua/includes/modules/` и `extensions/` видно, что доступны:

- `http` (`http.Fetch`, `http.Post`) — HTTP-запросы **наружу** (асинхронные).
- `net` (`extensions/net.lua`) — обмен **только клиент↔сервер GMod** (не наружу).
- `file` — чтение/запись файлов, но **в песочнице**: пути `DATA` (= `garrysmod/data`),
  `GAME`, `LUA`, `MOD`, `BSP`. Произвольные пути недоступны.
- `sql` (`util/sql.lua`) — SQLite (можно как «чёрный ящик» IPC, но это хак).
- `draw`, `render`, `surface`, `mesh` (IMesh/IVertex), `cam`, `effects`, `particles`,
  `util`, `usermessage`, `cookie`, `vgui`/`derma`.
- **Сырых сокетов (TCP/UDP) в штатном Lua нет.** Есть только `http` (наружу) и `net`
  (внутри GMod). Значит для низколатентного IPC нужен либо бинарный модуль, либо
  обходные пути (файл/SQLite/HTTP).

## Бинарные Lua-модули (низколатентный путь)

- GMod умеет подгружать нативные Lua-модули-DLL из `garrysmod/lua/bin/`
  (по умолчанию папка отсутствует). Префикс имени: `gmcl_` (клиент) / `gmsv_` (сервер).
- Модуль даёт Lua-коду полноценный нативный доступ (сокеты, shared memory, чтение
  процессов и т.п.). **Это путь для низкой задержки**, но требует сборки под разрядность
  GMod (x86-64 для `gmod_win64.exe`) и корректный ABI модулей GMod (Lua/LuaJIT).

## Рендер (чем делать 3D-вид)

- GMod/ Source рисует BSP-карту + сущности. Готовой карты под Diablo нет — уровень
  придётся строить **процедурно** или рисовать своим кодом.
- Клиентские хуки для кастомного рендера: `RenderScene`, `PostDrawOpaqueRenderables`,
  `PreDrawHUD`, `HUDPaint`, `RenderScreenspaceEffects`, `PostProcess`, `DrawPhysgunBeam` и др.
- Инструменты: сущности (`Entity`/`NextBot`/`prop_dynamic`), библиотека `mesh` (собственная
  геометрия без BSP), материалы/текстуры, `cam.Start3D`.
- UI: `derma` (VGUI) для инвентаря/панелей, `surface`/`draw` для полосков и текста.

## Ограничения, которые надо учитывать

- Нет динамической генерации BSP «на лету» в Lua; произвольную геометрию удобнее рисовать
  через `mesh` (клиентский рендер) или укладывать из моделей/брашей.
- Физика Source не подходит для тайловой логики Diablo — движение/коллизии проще
  считать самим в Lua по сетке.
- `file` ограничен песочницей → внешний процесс должен писать прямо в `garrysmod/data/`.
- `http.Fetch` асинхронный и не рассчитан на 60 Гц → для MVP файловый IPC, для продакшена —
  бинарный модуль с сокетом.

## Что это значит для нас

- **MVP без нативного кода:** внешний helper пишет JSON-снимок в `garrysmod/data/d1bridge/`,
  GMod-аддон читает `file.Read` и рендерит. Просто, но с задержкой и дисковым I/O.
- **Продакшен:** бинарный модуль `gmcl_d1bridge.dll` с сокетом/shared memory к TH4-мосту.
- **UI и логика представления** — целиком в Lua (аддон/гейммод).
