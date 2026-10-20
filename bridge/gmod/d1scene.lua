--[[--------------------------------------------------------------------------
    d1scene.lua  —  3D-сцена уровня TH4 в GMod (Фаза 2)

    Данные приходят из бинарного модуля d1bridge.dll (shared memory
    D1BridgeState). Никаких файлов.

    ГЕОМЕТРИЯ (важно!)
    ------------------
    Мир GMod — Z-up: X=восток, Y=север, Z=вверх.
    Горизонтальная плоскость — XY, пол лежит на Z=0.

    Клетка (Row, Col) -> мировая позиция:
        X = Col * CELL      (восток)
        Y = Row * CELL      (север)
        Z = 0               (высота)

    ИЗОМЕТРИЯ TH4
    -------------
    TH4 рисует карту так:
        px = (dRow - dCol) * 64
        py = (dRow + dCol) * 32      (py — вниз)

    Этот 2D-вид ВОСПРОИЗВОДИТСЯ в 3D камерой GMod при:
        yaw = 225°, pitch = +30° (смотрим вниз)
    Проверено расчётом: при такой камере проекция даёт ровно те же
    px/py, а «вперёд» камеры (W) совпадает с направлением PCMD_5
    (вверх по экрану TH4), «вправо» (D) — с PCMD_6.

    Базовый ракурс ставит d1control.lua (TH4_BASE_YAW/TH4_BASE_PITCH),
    мышь вращает камеру ОТНОСИТЕЛЬНО него. Поэтому по умолчанию
    3D-сцена — это ровно изометрия TH4 на настоящих данных уровня
    (FineMap / TileBlockWalking из shared memory).

    ОТРИСОВКА
    ---------
    В GMod mesh-API — immediate-mode IMesh (Begin/Position/Color/Quad/End),
    а не «Start/End». Рабочую сигнатуру определяем в runtime
    (см. d1meshprobe2.lua), потому что вариантов несколько.

    Что рисуем:
        - пол: квадратные плитки по клеткам (в изометрии -> ромбы)
        - стены: боксы (TileBlockWalking по ID тайла)
        - герой: бокс, повёрнутый по направлению движения
        - камера: от третьего лица, следует за героем

    Команды:
        d1scene_toggle        — показать/скрыть сцену
        d1scene_info          — инфо о загруженной карте
        d1scene_cam [h] [back] — высота и расстояние камеры
        d1scene_fov [f]       — поле зрения (меньше -> ближе к изометрии)
        d1scene_scale [m]     — масштаб мира
        d1scene_ascii [rows]  — ASCII-карта области (сверка с TH4)
--------------------------------------------------------------------------]]

-- ---------------------------------------------------------------- контроллер
-- d1control.lua даёт FPS-управление (камера + WASD относительно камеры).
-- Загружаем автоматически, если его ещё нет.
if not D1Control then
    local ok = pcall( dofile, "autorun/client/d1control.lua" )
    if not ok then
        print( "[d1scene] не удалось загрузить d1control.lua" )
    end
end

-- ---------------------------------------------------------------- модуль
-- Ищем модуль с read_map_area (нужен для локальной карты).
local MOD_NAMES = { "d1bridge", "d1bridge2" }
local REQUIRED_ABI = 2

local bridge = nil
for _, name in ipairs( MOD_NAMES ) do
    pcall( require, name )
    local m = (package and package.loaded) and package.loaded[name]
    if type(m) == "table" and m.abi_version and m.abi_version() >= REQUIRED_ABI
       and m.read_map_area then
        bridge = m
        break
    end
end

if not bridge then
    print( "[d1scene] нужен бинарный модуль d1bridge с read_map_area " ..
           "(abi >= " .. REQUIRED_ABI .. ")" )
    return
end

-- ---------------------------------------------------------------- константы
local CELL     = 64     -- размер клетки в 3D (должен совпадать с d1control)
local WALL_H   = 110    -- высота стены
local HERO_H   = 60     -- высота героя
local HERO_R   = 16     -- половина ширины героя

local RADIUS   = 22     -- сколько клеток читаем вокруг героя
local REFRESH  = 0.25   -- как часто перечитываем карту (сек)

-- Камера: высота = camBack * tan(30°), тогда герой ровно в центре экрана
-- при базовом ракурсе TH4 (pitch = 30°).
-- camBack/camHeight/fov подобраны так, чтобы нарисованная область
-- (RADIUS клеток) покрывала весь видимый кадр.
local camBack   = 1050   -- горизонтальное отступление назад
local camHeight = 606    -- высота (= camBack * tan30)
local fov       = 32     -- поле зрения

local FLOOR_BUCKETS = 5  -- сколько оттенков пола
local WALL_COLOR  = Color( 74, 68, 62, 255 )
local HERO_COLOR  = Color( 205, 65, 65, 255 )
local NOSE_COLOR  = Color( 255, 220, 90, 255 )
local MARKER_COLOR = Color( 255, 40, 200, 255 )

-- render.OverrideView* в этой сборке GMod отсутствует (проверено переписью
-- render: 142 функции, но без них).
local HAS_OVERRIDE = false
-- cam.Start3D — рабочий способ задать свой ракурс (проверено зондом).
local HAS_CAM3D = ( cam ~= nil and cam.Start3D ~= nil and cam.End3D ~= nil )

local BUCKET_COLOR = {
    Color( 118, 108,  92, 255 ),
    Color( 132, 118,  96, 255 ),
    Color( 104, 104, 100, 255 ),
    Color( 142, 126, 100, 255 ),
    Color(  96,  92,  88, 255 ),
}

-- ---------------------------------------------------------------- состояние
local enabled    = true
local mapData    = nil
local heroPos    = { x = 0, y = 0, z = 0 }
local heroYaw    = 0
local worldScale = 1
local builtFor   = nil   -- ключ карты, для которой собрана геометрия

-- Счётчики кадров (объявлены здесь, т.к. используются выше по файлу)
local frameCount = 0
local drawMsSum  = 0
local drawMsLast = 0

local floorQuads = {}   -- [bucket] = список квадов
local wallQuads  = {}

-- ---------------------------------------------------------------- якорь/камера
-- "player" — уровень рисуется ВОКРУГ игрока, камера штатная (вид от первого
--            лица, как в шутере). Герой всегда в центре кадра.
-- "iso"    — камера своя (cam.Start3D), ракурс TH4: yaw=225, pitch=30.
local CAM_MODE = "player"
local ANCHOR_MODE = "player"
local anchorX, anchorY = 0, 0
local builtAnchor = nil
local floorZ = 4

local calcViewCalled = false
local hookBroken     = false
local teleportEnabled = false   -- включается командой d1scene_teleport 1

-- ---------------------------------------------------------------- сетка
-- Клетка (row, col) -> центр в 3D (X, Y)
local function cellToWorld( row, col )
    local x = col * CELL * worldScale
    local y = row * CELL * worldScale
    if ANCHOR_MODE == "player" then
        -- Сдвиг так, чтобы герой оказался под игроком
        x = x - heroPos.x + anchorX
        y = y - heroPos.y + anchorY
    end
    return x, y
end

-- ---------------------------------------------------------------- квады
-- Квад = 12 чисел: 4 вершины по 3.
local function pushQuad( list, x1, y1, z1, x2, y2, z2, x3, y3, z3, x4, y4, z4 )
    local n = #list
    list[n+1]  = { x1, y1, z1, x2, y2, z2, x3, y3, z3, x4, y4, z4 }
end

-- Нормаль квада (по первым трём вершинам)
local function quadNormal( q )
    local ux, uy, uz = q[4]-q[1], q[5]-q[2], q[6]-q[3]
    local vx, vy, vz = q[7]-q[1], q[8]-q[2], q[9]-q[3]
    local nx = uy*vz - uz*vy
    local ny = uz*vx - ux*vz
    local nz = ux*vy - uy*vx
    local l = math.sqrt( nx*nx + ny*ny + nz*nz )
    if l > 0 then nx, ny, nz = nx/l, ny/l, nz/l end
    return nx, ny, nz
end

-- ---------------------------------------------------------------- сборка геометрии
-- Пол — квадратные плитки; стены — боксы (верх + 4 боковые грани).
local function buildGeometry()
    for i = 1, FLOOR_BUCKETS do floorQuads[i] = {} end
    wallQuads = {}
    if not mapData then return end

    local tiles = mapData.tiles
    local walls = mapData.walls
    local w = mapData.w
    local h = mapData.h
    local oRow = mapData.origin_row
    local oCol = mapData.origin_col

    local half = CELL * worldScale * 0.5
    local hh   = WALL_H * worldScale

    for dr = 0, h - 1 do
        for dc = 0, w - 1 do
            local idx = dr * w + dc + 1
            local tile = tiles[idx] or 0
            if tile ~= 0 then
                local x, y = cellToWorld( oRow + dr, oCol + dc )
                local isWall = (walls[idx] or 0) == 1

                if isWall then
                    -- Стена — бокс: 4 боковые грани + верх
                    local hw = half * 0.94
                    local x0, x1 = x - hw, x + hw
                    local y0, y1 = y - hw, y + hw
                    local z0, z1 = floorZ, floorZ + hh
                    -- северная (-Y)
                    pushQuad( wallQuads, x0, y0, z0, x1, y0, z0, x1, y0, z1, x0, y0, z1 )
                    -- восточная (+X)
                    pushQuad( wallQuads, x1, y0, z0, x1, y1, z0, x1, y1, z1, x1, y0, z1 )
                    -- южная (+Y)
                    pushQuad( wallQuads, x1, y1, z0, x0, y1, z0, x0, y1, z1, x1, y1, z1 )
                    -- западная (-X)
                    pushQuad( wallQuads, x0, y1, z0, x0, y0, z0, x0, y0, z1, x0, y1, z1 )
                    -- верх
                    pushQuad( wallQuads, x0, y0, z1, x1, y0, z1, x1, y1, z1, x0, y1, z1 )
                else
                    -- Пол — плитка. Разные типы тайлов -> разные оттенки.
                    local b = ( tile % FLOOR_BUCKETS ) + 1
                    local list = floorQuads[b]
                    pushQuad( list, x-half, y-half, floorZ, x+half, y-half, floorZ,
                                  x+half, y+half, floorZ, x-half, y+half, floorZ )
                end
            end
        end
    end
end

-- ---------------------------------------------------------------- отрисовка
-- Рабочий API mesh в GMod (проверено зондами d1meshprobe2/3):
--     mesh.Begin( primitiveType, count, [material] )
--     mesh.Normal( x, y, z ) / mesh.Color( r, g, b, a )
--     mesh.Quad( v1, v2, v3, v4 )     -- 4 Vector
--     mesh.End()
-- ВАЖНО 1: первый аргумент Begin — ТИП ПРИМИТИВА (малое число, напр. 4),
--          а не количество вершин. Иначе ошибка
--          "called mesh.Begin with a bad primitive type (...)".
-- ВАЖНО 2: если Begin не завершён End — следующий Begin падает с
--          "mesh.End must be called before calling mesh.Begin again".
--
-- Тип примитива и способ задания цвета определяем в runtime.
local DRAW      = nil
local PRIMITIVE = nil

-- Отрисовать список квадов одним батчем.
-- Временные Vector переиспользуются — иначе на кадр уходят десятки
-- тысяч аллокаций.
local TMP = { Vector( 0, 0, 0 ), Vector( 0, 0, 0 ), Vector( 0, 0, 0 ), Vector( 0, 0, 0 ) }

local function renderQuads( list, color, mode, pt )
    local n = #list
    if n == 0 then return end
    local nv = n * 4      -- вершин (4 на квад)

    if mode == "A2" then
        render.SetColorMaterial( color )
        mesh.Begin( pt, nv )
    else
        mesh.Begin( pt, nv, "Debug/DebugMaterial" )
    end

    if mode == "A3" then
        -- цвет вершин задаётся один раз на весь батч
        mesh.Color( color.r, color.g, color.b, color.a )
    end

    local t1, t2, t3, t4 = TMP[1], TMP[2], TMP[3], TMP[4]

    for i = 1, n do
        local q = list[i]
        local nx, ny, nz = quadNormal( q )
        mesh.Normal( nx, ny, nz )
        t1.x, t1.y, t1.z = q[1],  q[2],  q[3]
        t2.x, t2.y, t2.z = q[4],  q[5],  q[6]
        t3.x, t3.y, t3.z = q[7],  q[8],  q[9]
        t4.x, t4.y, t4.z = q[10], q[11], q[12]
        mesh.Quad( t1, t2, t3, t4 )
    end

    mesh.End()
end

local function detectDraw()
    if not ( mesh and mesh.Begin and mesh.End and mesh.Quad ) then
        print( "[d1scene] mesh-API недоступен — сцена не будет отрисована" )
        return
    end

    -- Сначала закрыть «зависший» меш (например, оставшийся от другого скрипта)
    pcall( function() mesh.End() end )

    local test = { { 0, 0, 0,  1, 0, 0,  1, 1, 0,  0, 1, 0 } }
    for pt = 0, 12 do
        for _, mode in ipairs( { "A2", "A3" } ) do
            local ok, err = pcall( renderQuads, test, Color( 255, 255, 255, 255 ), mode, pt )
            pcall( function() mesh.End() end )
            if ok then
                DRAW = mode
                PRIMITIVE = pt
                print( "[d1scene] mesh: тип примитива=" .. pt .. ", режим " .. mode )
                return
            end
        end
    end

    print( "[d1scene] подходящий тип примитива не найден" )
end

-- Отрисовать список квадов рабочим способом.
-- Ограничение движка: в одном Begin не больше 32768 вершин,
-- поэтому длинные списки режем на куски.
local MAX_QUADS_PER_BATCH = 8000

local errCount = 0
local function drawQuads( list, color )
    if not DRAW then return end
    local n = #list
    if n == 0 then return end

    local from = 1
    while from <= n do
        local to = from + MAX_QUADS_PER_BATCH - 1
        if to > n then to = n end
        local chunk = {}
        for i = from, to do chunk[#chunk+1] = list[i] end

        local ok, err = pcall( renderQuads, chunk, color, DRAW, PRIMITIVE )
        if not ok then
            pcall( function() mesh.End() end )
            errCount = errCount + 1
            if errCount <= 3 then
                print( "[d1scene] drawQuads: " .. tostring( err ) )
            elseif errCount == 4 then
                print( "[d1scene] drawQuads: дальше ошибки не печатаю" )
            end
            return
        end
        from = to + 1
    end
end

-- Герой: бокс, повёрнутый по направлению движения + «носок»
local heroQuads  = {}
local noseQuads  = {}

local function buildHeroGeometry()
    heroQuads = {}
    noseQuads = {}

    local hx, hy = heroPos.x, heroPos.y
    local hr  = HERO_R * worldScale
    local hgt = HERO_H * worldScale

    local rad = math.rad( heroYaw )
    local cs, sn = math.cos( rad ), math.sin( rad )
    local fwdX, fwdY = cs, sn
    local rgtX, rgtY = -sn, cs

    -- 4 угла основания
    local c = { { -hr, -hr }, { hr, -hr }, { hr, hr }, { -hr, hr } }
    local b = {}
    for i = 1, 4 do
        b[i] = { hx + rgtX*c[i][1] + fwdX*c[i][2],
                 hy + rgtY*c[i][1] + fwdY*c[i][2] }
    end

    for i = 1, 4 do
        local j = (i % 4) + 1
        -- боковая грань
        pushQuad( heroQuads,
            b[i][1], b[i][2], 0, b[j][1], b[j][2], 0,
            b[j][1], b[j][2], hgt, b[i][1], b[i][2], hgt )
    end
    -- верх
    pushQuad( heroQuads,
        b[1][1], b[1][2], hgt, b[2][1], b[2][2], hgt,
        b[3][1], b[3][2], hgt, b[4][1], b[4][2], hgt )

    -- «носок» — куда смотрит герой
    local nx = hx + fwdX * ( hr * 2.0 )
    local ny = hy + fwdY * ( hr * 2.0 )
    local nz = hgt * 0.45
    pushQuad( noseQuads,
        hx + rgtX*hr*0.5, hy + rgtY*hr*0.5, nz,
        hx - rgtX*hr*0.5, hy - rgtY*hr*0.5, nz,
        nx, ny, nz,
        nx, ny, nz )
end

-- ---------------------------------------------------------------- чтение карты
local function refreshMap()
    if not bridge or not bridge.read then return end
    local p = bridge.read()
    if not p then return end

    local x, y = cellToWorld( p.Row, p.Col )
    heroPos.x, heroPos.y, heroPos.z = x, y, floorZ
    if D1Control then
        heroYaw = D1Control.GetHeroYaw()
    end

    local area = bridge.read_map_area( p.Row, p.Col, RADIUS )
    if not area then return end

    -- Ключ области: если не изменилась — геометрию пересобирать не нужно
    local key = string.format( "%d:%d:%d:%d:%d", area.origin_row, area.origin_col,
        area.w, area.h, worldScale )
    local akey = string.format( "%.0f:%.0f:%.0f", anchorX, anchorY, floorZ )
    mapData = area
    if key ~= builtFor or akey ~= builtAnchor then
        builtFor = key
        builtAnchor = akey
        buildGeometry()
    end
end

-- Привязать уровень к позиции игрока (режим "player")
local function updateAnchor()
    if ANCHOR_MODE ~= "player" then return end
    local ply = Entity( 1 )
    if not ply or not ply:IsValid() then return end
    local p = ply:GetPos()
    if math.abs( p.x - anchorX ) > 4 or math.abs( p.y - anchorY ) > 4 then
        anchorX, anchorY = p.x, p.y
        builtFor = nil
        refreshMap()
    end
end

-- ---------------------------------------------------------------- камера
local playerHidden = false
local camOrigin = nil
local camAngles = nil

local function hidePlayer()
    if playerHidden then return end
    local ply = Entity( 1 )
    if not ply or not ply:IsValid() then return end
    pcall( function() ply:SetNoDraw( true ) end )
    pcall( function() ply:DrawShadow( false ) end )
    playerHidden = true
end

local function showPlayer()
    if not playerHidden then return end
    local ply = Entity( 1 )
    if ply and ply:IsValid() then
        pcall( function() ply:SetNoDraw( false ) end )
        pcall( function() ply:DrawShadow( true ) end )
    end
    playerHidden = false
end

-- Рассчитать положение камеры: сзади-сверху относительно героя,
-- в базовом ракурсе TH4 (yaw 225, pitch 30) + поворот мышью.
local function computeCamera()
    local yaw, pitch, fx, fy
    if D1Control then
        yaw   = D1Control.GetYaw()
        pitch = D1Control.GetPitch()
        fx, fy = D1Control.GetBasis()
    else
        yaw   = heroYaw
        pitch = 30
        local rad = math.rad( yaw )
        fx, fy = math.cos( rad ), math.sin( rad )
    end

    -- Отступаем назад по направлению обзора (в горизонтальной плоскости)
    local ox = heroPos.x - fx * camBack
    local oy = heroPos.y - fy * camBack

    camOrigin = Vector( ox, oy, heroPos.z + camHeight )
    camAngles = Angle( pitch, yaw, 0 )
end

-- Способ 1: хук CalcView. В этой сборке GMod он вызывается НЕРЕГУЛЯРНО
-- (перепись хуков: 0 вызовов за 656 кадров), поэтому он только дополняет.
local calcViewStamp = 0
hook.Add( "CalcView", "d1scene_view", function()
    calcViewStamp = frameCount
    if not enabled then return end
    if ANCHOR_MODE ~= "world" then return end
    computeCamera()
    return camOrigin, camAngles, fov
end )

-- Способ 2: перенести самого игрока в точку камеры.
-- Если переопределить вид нечем — «телепортируем» игрока: SetPos/SetEyeAngles
-- есть в любой версии. Сервер будет Try слегка возвращать позицию, но
-- каждый кадр мы ставим её заново, так что взгляд остаётся нужным.
local function teleportCamera()
    local ply = Entity( 1 )
    if not ply or not ply:IsValid() then return end
    pcall( function() ply:SetPos( camOrigin ) end )
    pcall( function() ply:SetEyeAngles( camAngles ) end )
    pcall( function() ply:SetVelocity( Vector( 0, 0, 0 ) ) end )
end

local function setupCamera()
    -- В режиме "player" камера и FOV штатные GMod — вид от первого лица.
    if CAM_MODE ~= "iso" then return end

    computeCamera()

    if HAS_OVERRIDE then
        render.OverrideViewOrigin( camOrigin )
        render.OverrideViewAngles( camAngles )
        render.ClearViewModel()
    end

    -- Узкое поле зрения -> вид ближе к ортогональной изометрии TH4
    local ply = Entity( 1 )
    if ply and ply:IsValid() then
        pcall( function() ply:SetFOV( fov ) end )
    end

    -- Если CalcView не срабатывает (последний вызов давно) — двигаем игрока.
    -- По умолчанию ВЫКЛЮЧЕНО: сервер откатывает позицию, игрок падает и
    -- «умирает» (suicided). Включается командой d1scene_teleport 1.
    if teleportEnabled and frameCount - calcViewStamp > 10 then
        teleportCamera()
    end
end

-- «Маяк» — яркий столб в точке героя. Нужен, чтобы сразу видеть,
-- где именно нарисован уровень (и что камера туда смотрит).
local markerQuads = {}

local function buildMarker()
    markerQuads = {}
    local hx, hy = heroPos.x, heroPos.y
    local hz = heroPos.z
    local w = 14
    local h = 260
    local x0, x1 = hx - w, hx + w
    local y0, y1 = hy - w, hy + w
    local z0, z1 = hz, hz + h
    pushQuad( markerQuads, x0, y0, z0, x1, y0, z0, x1, y0, z1, x0, y0, z1 )
    pushQuad( markerQuads, x1, y0, z0, x1, y1, z0, x1, y1, z1, x1, y0, z1 )
    pushQuad( markerQuads, x1, y1, z0, x0, y1, z0, x0, y1, z1, x1, y1, z1 )
    pushQuad( markerQuads, x0, y1, z0, x0, y0, z0, x0, y0, z1, x0, y1, z1 )
    pushQuad( markerQuads, x0, y0, z1, x1, y0, z1, x1, y1, z1, x0, y1, z1 )
end

-- ---------------------------------------------------------------- кадр
-- Своя камера — через cam.Start3D. CalcView в этой сборке вызывается,
-- но его значения возврата игнорируются, а render.OverrideView* отсутствует.
-- cam.Start3D работает и даёт полный контроль над ракурсом.
local frameCount  = 0
local drawMsSum   = 0
local drawMsLast  = 0

local function renderScene()
    if not enabled then
        showPlayer()
        return
    end
    hidePlayer()
    if not mapData then return end
    if not DRAW then detectDraw() end
    if not DRAW then return end

    local t0 = SysTime()

    local useCam = ( CAM_MODE == "iso" )
    if useCam then
        -- Убираем глубину от песочницы, чтобы она не перекрывала уровень,
        -- а внутри блока камеры глубина снова работает — значит стены
        -- перекрываются правильно сами (без ручной сортировки).
        pcall( function() render.ClearDepth() end )
        cam.Start3D( camOrigin, camAngles, 1 )
    end

    for i = 1, FLOOR_BUCKETS do
        drawQuads( floorQuads[i] or {}, BUCKET_COLOR[i] )
    end
    drawQuads( wallQuads, WALL_COLOR )

    buildHeroGeometry()
    buildMarker()
    drawQuads( heroQuads, HERO_COLOR )
    drawQuads( noseQuads, NOSE_COLOR )
    drawQuads( markerQuads, MARKER_COLOR )

    if useCam then cam.End3D() end

    drawMsLast = ( SysTime() - t0 ) * 1000
    drawMsSum  = drawMsSum + drawMsLast
    frameCount = frameCount + 1
end

-- CalcView в этой сборке вызывается, но его значения возврата игнорируются,
-- поэтому камера задаётся через cam.Start3D (см. renderScene).
local function checkCameraMode()
    if calcViewStamp > 0 then return end
    if frameCount == 60 then
        print( "[d1scene] CalcView игнорируется -> камера через cam.Start3D" )
    end
end

-- ---------------------------------------------------------------- инициализация
-- Начальный якорь — позиция игрока (в режиме "player" уровень вокруг него)
do
    local ply = Entity( 1 )
    if ply and ply:IsValid() then
        local p = ply:GetPos()
        anchorX, anchorY = p.x, p.y
    end
end

refreshMap()
timer.Create( "d1scene_refresh", REFRESH, 0, refreshMap )

-- Где рисовать. Перепись хуков этой сборки GMod показала:
--   работают:   Think, Tick, PreRender, PostRender, RenderScene, DrawOverlay
--   НЕ работают: PreDraw, PostDraw, HUDPaint, CalcView, ViewVectors
-- Меш-батч положено отправлять в рендер-фазе -> RenderScene.
-- Если он не сработает — рисуем из Think.
local renderSceneSeen = false

-- Тела хуков обёрнуты в pcall: ошибка (например, nil-глобал) не должна
-- сыпать сообщениями каждый кадр и не должна ломать сцену.
local function safe( fn )
    if hookBroken then return end
    local ok, err = pcall( fn )
    if not ok then
        hookBroken = true
        print( "[d1scene] хук отключён из-за ошибки: " .. tostring( err ) )
    end
end

hook.Add( "RenderScene", "d1scene_render", function()
    renderSceneSeen = true
    safe( function()
        if not enabled then
            showPlayer()
            return
        end
        hidePlayer()
        setupCamera()
        renderScene()
    end )
end )

hook.Add( "Think", "d1scene_think", function()
    safe( function()
        checkCameraMode()
        updateAnchor()
        if renderSceneSeen then return end
        if not enabled then
            showPlayer()
            return
        end
        hidePlayer()
        setupCamera()
        renderScene()
    end )
end )

-- ---------------------------------------------------------------- команды
concommand.Add( "d1scene_toggle", function()
    enabled = not enabled
    if not enabled then showPlayer() end
    chat.AddText( Color( 70, 200, 110 ), "[d1scene] ",
        Color( 230, 230, 235 ), enabled and "сцена показана" or "сцена скрыта" )
end )

concommand.Add( "d1scene_info", function()
    if not mapData then
        chat.AddText( Color( 230, 180, 60 ), "[d1scene] карта не загружена" )
        return
    end
    local walls = 0
    local floors = 0
    for i = 1, #mapData.walls do
        if mapData.walls[i] == 1 then walls = walls + 1 end
    end
    for i = 1, #mapData.tiles do
        if (mapData.tiles[i] or 0) ~= 0 then floors = floors + 1 end
    end
    local hr, hc = 0, 0
    local yaw, pitch = 0, 0
    if D1Control then
        hr, hc = D1Control.GetHeroCell()
        yaw, pitch = D1Control.GetYaw(), D1Control.GetPitch()
    end

    -- Экранные координаты TH4 для героя (для сверки с оригиналом)
    local th4x = ( hr - hc ) * 64
    local th4y = ( hr + hc ) * 32

    chat.AddText( Color( 70, 200, 110 ), "[d1scene] " )
    chat.AddText( Color( 230, 230, 235 ), string.format(
        "область %dx%d (R%d..%d, C%d..%d) пол=%d стен=%d",
        mapData.w, mapData.h,
        mapData.origin_row, mapData.origin_row + mapData.h - 1,
        mapData.origin_col, mapData.origin_col + mapData.w - 1,
        floors, walls ) )
    chat.AddText( Color( 230, 230, 235 ), string.format(
        "герой R%d C%d -> 3D (%.0f, %.0f), TH4-экран (%.0f, %.0f)",
        hr, hc, heroPos.x, heroPos.y, th4x, th4y ) )
    local avg = 0
    if frameCount > 0 then avg = drawMsSum / frameCount end

    chat.AddText( Color( 230, 230, 235 ), string.format(
        "камера yaw=%.0f pitch=%.0f fov=%d back=%d h=%d  mesh=%s кадров=%d",
        yaw, pitch, fov, camBack, camHeight, tostring( DRAW ), frameCount ) )
    chat.AddText( Color( 230, 230, 235 ), string.format(
        "режим=%s камера=%s  RenderScene=%s  якорь=(%.0f, %.0f)",
        ANCHOR_MODE, CAM_MODE, tostring( renderSceneSeen ), anchorX, anchorY ) )
    chat.AddText( Color( 230, 230, 235 ), string.format(
        "отрисовка: последний %.2f мс, средний %.2f мс", drawMsLast, avg ) )
    local nq = #wallQuads
    for i = 1, FLOOR_BUCKETS do nq = nq + #( floorQuads[i] or {} ) end
    chat.AddText( Color( 230, 230, 235 ), string.format(
        "квадов на кадр: %d (примитив=%s)", nq, tostring( PRIMITIVE ) ) )
end )

concommand.Add( "d1scene_cammode", function( _, _, args )
    local m = args[1]
    if m == "player" or m == "iso" then
        CAM_MODE = m
        ANCHOR_MODE = ( m == "player" ) and "player" or "world"
        floorZ = ( m == "player" ) and 4 or 0
        anchorX, anchorY = 0, 0
        builtFor = nil
        builtAnchor = nil
        refreshMap()
        chat.AddText( Color( 70, 200, 110 ), "[d1scene] режим камеры: " .. m ..
            ( m == "player" and " (вид от первого лица)" or " (изометрия TH4)" ) )
    else
        chat.AddText( Color( 230, 180, 60 ), "[d1scene] usage: d1scene_cammode player|iso" )
    end
end )

concommand.Add( "d1scene_teleport", function( _, _, args )
    teleportEnabled = ( tonumber( args[1] ) or 0 ) ~= 0
    chat.AddText( Color( 70, 200, 110 ), "[d1scene] перенос игрока: " ..
        ( teleportEnabled and "вкл" or "выкл" ) )
end )

concommand.Add( "d1scene_anchor", function( _, _, args )
    local mode = args[1]
    if mode == "player" or mode == "world" then
        ANCHOR_MODE = mode
        floorZ = ( mode == "player" ) and 4 or 0
        builtFor = nil
        refreshMap()
        chat.AddText( Color( 70, 200, 110 ), "[d1scene] режим привязки: " .. mode )
    else
        chat.AddText( Color( 230, 180, 60 ), "[d1scene] usage: d1scene_anchor world|player" )
    end
end )

concommand.Add( "d1scene_cam", function( _, _, args )
    camBack   = tonumber( args[1] ) or camBack
    camHeight = tonumber( args[2] ) or camHeight
    chat.AddText( Color( 70, 200, 110 ), "[d1scene] камера: назад=" .. camBack ..
        " высота=" .. camHeight )
end )

concommand.Add( "d1scene_fov", function( _, _, args )
    fov = math.Clamp( tonumber( args[1] ) or fov, 20, 120 )
    chat.AddText( Color( 70, 200, 110 ), "[d1scene] FOV: " .. fov )
end )

concommand.Add( "d1scene_scale", function( _, _, args )
    worldScale = tonumber( args[1] ) or 1
    builtFor = nil          -- force rebuild
    refreshMap()
    chat.AddText( Color( 70, 200, 110 ), "[d1scene] масштаб: " .. worldScale )
end )

-- ASCII-карта области — для сверки с TH4 (та же раскладка, что у TH4)
concommand.Add( "d1scene_ascii", function( _, _, args )
    if not mapData then
        chat.AddText( Color( 230, 180, 60 ), "[d1scene] карта не загружена" )
        return
    end
    local rows = math.Clamp( tonumber( args[1] ) or 24, 4, 64 )
    local tiles = mapData.tiles
    local walls = mapData.walls
    local w = mapData.w
    local h = mapData.h
    local hr, hc = 0, 0
    if D1Control then hr, hc = D1Control.GetHeroCell() end

    local out = {}
    for dr = 0, h - 1 do
        local line = {}
        for dc = 0, w - 1 do
            local idx = dr * w + dc + 1
            local ch
            if mapData.origin_row + dr == hr and mapData.origin_col + dc == hc then
                ch = "@"
            elseif (walls[idx] or 0) == 1 then
                ch = "#"
            elseif (tiles[idx] or 0) == 0 then
                ch = " "
            else
                ch = "."
            end
            line[#line+1] = ch
        end
        out[#out+1] = table.concat( line )
    end
    local chunk = {}
    for i = 1, #out do
        chunk[#chunk+1] = out[i]
        if #chunk >= rows then
            chat.AddText( Color( 200, 220, 255 ), "[d1scene] " ..
                table.concat( chunk, "\n" ) )
            chunk = {}
        end
    end
    if #chunk > 0 then
        chat.AddText( Color( 200, 220, 255 ), "[d1scene] " ..
            table.concat( chunk, "\n" ) )
    end
end )

print( "[d1scene] 3D-сцена уровня загружена. " ..
       "Команды: d1scene_toggle, d1scene_info, d1scene_cam, d1scene_fov, d1scene_ascii" )
