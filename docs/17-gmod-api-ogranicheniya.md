# 17. Ограничения API GMod (этой сборки) — что работает, а что нет

**Почему отдельный документ.** Всё это выяснялось зондами по одному пункту за
итерацию, потерять его — значит повторить недели работы. Документ проверен
экспериментально в клиенте GMod (сборка `gmod_win64`, gamemode `sandbox`).

> Метод: маленький скрипт-зонд в `garrysmod/lua/autorun/client/`, запуск
> `lua_openscript_cl "autorun/client/<файл>.lua"`, вывод в консоль + на экран.
> Все зонды лежат в `bridge/gmod/` и ставятся в GMod копированием.

---

## 1. Хуки: что вызывается, что нет

Проверено переписью хуков (`bridge/gmod/d1hookcensus.lua`, команда `d1census`).

### Работают

| Хук | Комментарий |
|-----|-------------|
| `Think` | основной хук логики, вызывается всегда |
| `Tick` | |
| `SetupMove`, `Move` | |
| `PreRender`, `PostRender` | рендер-фаза |
| **`RenderScene`** | **единственное рабочее место для отправки IMesh-батча** |
| `DrawOverlay` | единственное рабочее место для 2D-отрисовки |
| `HUDShouldDraw` | |

### НЕ вызываются (в отличие от обычного GMod!)

| Хук | Последствие |
|-----|-------------|
| `PreDraw`, `PostDraw` | нет 3D-вывода «до/после кадра» |
| **`HUDPaint`** | нет обычного HUD (текст, панели) — только `DrawOverlay` |
| **`CalcView`** | вызывается, но **значения возврата игнорируются** — камеру не переопределить |
| `ViewVectors`, `CalcPostView` | |
| `RenderScreenshots` | |
| `DrawHUD` | |
| `PlayerButtonPress`, `PlayerMouseWheel`, `ChatText` | |

**Вывод:** весь клиентский UI/вывод придётся делать через `DrawOverlay`,
а 3D-геометрию — отправлять в `RenderScene`.

---

## 2. Библиотека `mesh` — это immediate-mode IMesh, а не «Start/End»

Полный набор функций в этой сборке:

```
AdvanceVertex, Begin, BoneData, Color, End, Normal, Position, Quad, QuadEasy,
Specular, TangentS, TangentT, TexCoord, UserData, VertexCount
```

### Сигнатуры (проверено зондом `d1meshprobe2/4.lua`)

| Вызов | Итог |
|-------|------|
| `mesh.Begin( type, count, [material] )` | ✅ `type` = **тип примитива 0..7**, `count` = **число вершин** (макс. **32768**), `material` = строка или объект `Material` (необязателен) |
| `mesh.Quad( v1, v2, v3, v4 )` | ✅ 4 × `Vector` |
| `mesh.Quad()` | ❌ требует хотя бы 1 `Vector` |
| `mesh.QuadEasy( … )` | ❌ 3-й аргумент — **число**, а не `Vector`; неудобно |
| `mesh.Normal( x,y,z )` / `Normal(Vector)` | ✅ |
| `mesh.Position( x,y,z )` / `Position(Vector)` | ✅ |
| `mesh.Color( r,g,b,a )` | ✅ ровно 4 числа (объект `Color` не принимается) |
| `mesh.TexCoord( u,v )`, `mesh.AdvanceVertex()`, `mesh.VertexCount()` | ✅ |
| `mesh.Start( name )` | ❌ **не существует** (старый API) |
| `mesh.Clear` | ❌ не существует |
| `mesh.SetColor` | ❌ не существует (есть `mesh.Color`) |

### Типичные ошибки и их тексты

| Ошибка | Причина |
|--------|---------|
| `called mesh.Begin with a bad primitive type (20) or count (30)` | первым аргументом передали не тип примитива (допустимо **0..7**), а число вершин |
| `called mesh.Begin with a primitive count which results in too many vertices (60001, maximum=32768)` | `count` больше 32767 |
| `mesh.End must be called before calling mesh.Begin again` | не закрыли меш: после `Begin` обязателен `End` (в т.ч. в `pcall`-обработчике ошибок) |

### Рабочий скелет

```lua
mesh.Begin( 0, nVerts, "Debug/DebugMaterial" )   -- 0 = TRIANGLE_LIST
mesh.Color( r, g, b, a )                          -- цвет на весь батч
for each quad:
    mesh.Normal( nx, ny, nz )
    mesh.Quad( v1, v2, v3, v4 )                    -- 4 Vector
mesh.End()
```

* `render.SetColorMaterial( color )` + `mesh.Begin( type, count )` (2 аргумента)
  тоже работает — цвет берётся из текущего материала. **Режим `A2`** надёжнее
  `A3` (цвет вершин), т.к. не зависит от `$vertexcolor` у материала.
* Батчи >32768 вершин надо резать на куски (в `d1scene.lua` — по 8000 квадов).

---

## 3. Библиотека `render` — полная, но БЕЗ управления камерой

В `render` 142 функции — стандартный клиентский набор Source. **Но отсутствуют:**

```
render.OverrideViewOrigin
render.OverrideViewAngles
render.OverrideViewFOV
render.DrawMesh
```

Значит переопределить камеру «штатным» способом нельзя.

**Работающая замена — `cam.Start3D`:**

```lua
render.ClearDepth()                 -- глубина есть, но песочница мешает
cam.Start3D( camOrigin, camAngles, 1 )
    ... отправка IMesh-батча ...
cam.End3D()
```

Проверено визуально: зонд `d1renderprobe.lua` рисовал куб «снизу» обычным
IMesh и «сверху» — внутри `cam.Start3D`; виден был именно второй ✓.
То есть **свою камеру задать можно** — блок `cam.Start3D` меняет ракурс.

Прочее полезное из `render`: `ClearDepth`, `SetColorMaterial`, `DrawBox`,
`DrawSphere`, `DrawLine`, `DrawBeam`, `GetViewSetup`, `Model`, `MaterialOverride`.

---

## 4. Библиотека `surface` — полигоны НЕ рисуются

| Вызов | Итог |
|-------|------|
| `surface.DrawRect` | ✅ работает |
| `surface.DrawTexturedRectRotated` | ✅ работает (рисует **текущую привязанную текстуру** — если она не задана, выводит, например, текстуру HUD) |
| `surface.DrawTexturedRect`, `DrawTexturedRectUV` | ✅ работают |
| **`surface.DrawPoly`** | ❌ **не рисует вообще** (проверено 5 вариантов: вложенный/плоский формат, оба направления обхода, `Vector` вместо таблиц) |

**Вывод:** 2D-полигоны недоступны. Если нужен произвольный многоугольник —
либо IMesh (3D), либо текстура-атлас + `DrawTexturedRectUV` (2D).

---

## 5. Прочее

| Что | Факт |
|-----|------|
| `hook.Remove( event, id )` | **нужны оба аргумента**; с одним — ошибка `attempt to index local 'name'` |
| `ply:SetEyeAngles( … )` | **не применимо** — сервер владеет игроком, угол сбрасывается. Как база отсчёта использовать только *фактические* `EyeAngles()` |
| `ply:SetPos( … )` | клиентский «телепорт» сервер откатывает → игрок падает и умирает (`suicided`) |
| `Entity(1):GetPos()` / `:EyeAngles()` | работают ✓ (нужны для «якоря» и базы обзора) |
| `Material( "materials/….tga" )` | файл, записанный в runtime через `file.Write`, **не подхватился** (нужна диагностика; возможно, материальная система не перечитывает каталог после старта) |
| `file.Write( name, data, "GAME" )` | бинарные данные (с `\0`) пишутся нормально; `file.CreateDir` нужен для подкаталога |
| `bit` | библиотека доступна (нужна для CRC32 в самодельном PNG) |
| `ScrW()/ScrH()` | работают и в `DrawOverlay` ✓ |

---

## 6. Практические выводы (как рисовать 3D в этой сборке)

1. Отправлять геометрию — **в `RenderScene`**.
2. Свою камеру — **через `cam.Start3D`**, а не `CalcView`/`OverrideView*`.
3. `render.ClearDepth()` перед блоком камеры — иначе перекрывает глубина
   песочницы (внутри блока глубина работает, стены сортируются сами).
4. Цвет — через `render.SetColorMaterial` + `mesh.Begin(type, count)`.
5. 2D-интерфейс — через `DrawOverlay` (обычный `HUDPaint` молчит).
6. Если сервер **наш** — надёжнее рисовать уровень **серверными энтытями**:
   камера, свет, тени и ввод становятся штатными, и все перечисленные
   ограничения перестают matter.

---

## 7. Зонды (лежат в `bridge/gmod/`, копируются в GMod)

| Файл | Что проверяет |
|------|---------------|
| `d1meshprobe.lua` | общий обзор `render`/`cam`/`surface`, версии хуков |
| `d1meshprobe2.lua` | сигнатуры `mesh.*` (вызовом с неверным типом) |
| `d1meshprobe3.lua` | полный список `render`/`cam`/`surface`, методы игрока |
| `d1meshprobe4.lua` | типы примитива, смысл `count`, границы `count` |
| `d1polyprobe.lua` | форматы/обходы `surface.DrawPoly` (не рисует) |
| `d1renderprobe.lua` | рисует ли IMesh, работает ли `cam.Start3D` |
| `d1hookcensus.lua` | перепись хуков (команда `d1census`) |

Зонды **снимают сами себя** (`hook.Remove("RenderScene", "имя")`), чтобы старые
версии не сыпали ошибками каждый кадр.
