# Патчи к исходникам TH4

Исходники TH4 лежат в `vendor/the-hell-4-src` как **git-submodule**
(https://github.com/roboserg/the-hell-4-src.git, коммит `e8d0cc7`) — это
upstream-клон, который мы **не модифицируем в коммитах**.

Все наши правки внутри TH4 хранятся здесь, в виде патча.

## Что в патче

`0001-th4-shm-bridge.patch` — доработка TH4 для моста:

| Файл | Изменение |
|------|-----------|
| `src/d1bridge.cpp` | **новый**: публикация состояния в разделяемую память `D1BridgeState` (герой, `FineMap`, `TileBlockWalking`, `PlayerMap`, `CurAction`; seqlock) |
| `src/d1export.cpp` | **новый**: экспорт адресов/смещений (`d1map_export.txt`) для отладочных инструментов |
| `src/Main.cpp` | вызов инициализации моста |
| `src/funcs.h` | объявления функций моста |
| `thehell3.vcxproj` | добавление файлов в проект |
| `lib/SmackW32.DLL` | пропатченная библиотека (бинарная часть патча) |

## Как применить

```bash
git clone --recurse-submodules https://github.com/burymm/diablo3d.git
cd diablo-1-source
bridge\th4-patches\apply_patches.bat
```

Скрипт сначала пробует строгое применение патча, а если не выходит
(патч записан с LF, а checkout submodule может быть с CRLF при
`core.autocrlf=true`) — повторяет с `--ignore-whitespace`.
Проверено на чистом checkout'е коммита `e8d0cc7`: патч применяется,
`src/d1bridge.cpp` и `src/d1export.cpp` создаются, `lib/SmackW32.DLL`
совпадает побайтно.

## После применения — собрать TH4

```bash
cd bridge\reader
build_th43d.bat          # нужен MSBuild с toolset v145 (VS2019 BuildTools НЕ подходит)
```

Собранный `th43d.exe` кладётся в `e:\games\TheHell3D\` (тестовая копия).
Установленная игра `e:\games\The Hell IV` — **не трогать** (сейвы/язык).

## Проверить, что патч применён

```bash
git -C vendor/the-hell-4-src status --short
# должно быть:
#  M src/Main.cpp
#  M src/funcs.h
#  M thehell3.vcxproj
#  M lib/SmackW32.DLL
#  M src/d1bridge.cpp
#  M src/d1export.cpp
```
