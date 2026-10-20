--[[--------------------------------------------------------------------------
    d1control.lua  —  управление в стиле FPS: камера + движение относительно камеры

    Что делает:
      - камера вращается мышью (штатный mlook GMod, без захвата курсора);
      - WASD двигает героя ОТНОСИТЕЛЬНО текущего направления камеры;
      - модель героя в 3D поворачивается плавно (в TH4 — дискретно, 8 направлений);
      - команды уходят в TH4 нативно через shared memory (walkPath),
        без кликов и без задержки ввода.

    ГЕОМЕТРИЯ (важно!)
    ------------------
    Мир в GMod — Z-up! X=восток, Y=север, Z=вверх.
    Горизонтальная плоскость — XY, пол лежит на Z=0.

        X = Col * CELL      (восток)
        Y = Row * CELL      (север)

    В таком мире 8 направлений TH4 ложатся РОВНО через 45°, поэтому
    «ближайшее направление» ищется без приближений.

    Направления TH4 -> шаг в сетке (dRow, dCol) -> вектор в 3D (X, Y):
        PCMD_1 up-right    dRow= 0 dCol=-1  ->  (-1,  0)  180°
        PCMD_2 up-left     dRow=-1 dCol= 0  ->  ( 0, -1)  270°
        PCMD_3 down-right  dRow=+1 dCol= 0  ->  ( 0, +1)   90°
        PCMD_4 down-left   dRow= 0 dCol=+1  ->  (+1,  0)    0°
        PCMD_5 up          dRow=-1 dCol=-1  ->  (-1, -1)  225°
        PCMD_6 right       dRow=+1 dCol=-1  ->  (-1, +1)  135°
        PCMD_7 down        dRow=+1 dCol=+1  ->  (+1, +1)   45°
        PCMD_8 left        dRow=-1 dCol=+1  ->  (+1, -1)  315°

    (dRow/dCol взяты из changeRow/changeCol в StartWalk*, Player.cpp:6051-6058)

    ИЗОМЕТРИЯ TH4
    -------------
    TH4 рисует карту изометрически:
        px = (dRow - dCol) * 64
        py = (dRow + dCol) * 32      (py — вниз)

    Этот вид ТОЧНО воспроизводится камерой GMod при
        yaw = 225°, pitch = +30° (смотрим вниз)
    — проверено расчётом. В этом ракурсе:
        "вперёд" камеры (W) -> PCMD_5 (вверх по экрану TH4)
        "вправо" камеры (D) -> PCMD_6 (вправо по экрану TH4)
    Поэтому базовый ракурс камеры — 225°/30°, а мышь вращает её
    ОТНОСИТЕЛЬНО него (TH4_BASE_YAW / TH4_BASE_PITCH).

    Непрерывное движение:
      Нативный шаг в TH4 — ОДНА клетка. Чтобы идти непрерывно, команду
      отправляем повторно, как только герой дошагал (CurAction == 0)
      и клавиша всё ещё зажата.

    API (для d1scene.lua):
        D1Control.GetYaw()      — угол камеры
        D1Control.GetPitch()    — наклон камеры
        D1Control.GetHeroYaw()  — плавный угол модели героя
        D1Control.GetHeroPos()  — X, Y, Z героя
        D1Control.GetHeroCell() — Row, Col героя
        D1Control.IsMoving()    — движется ли герой
        D1Control.GetBasis()    — forwardXY, rightXY камеры

    Команды:
        d1_capture       — захват курсора (в GMod-клиенте недоступен)
        d1_turn [y] [p]  — ручное смещение обзора
        d1_look          — текущие углы
        d1_debug         — диагностика ввода
--------------------------------------------------------------------------]]

local MOD_NAMES = { "d1bridge", "d1bridge2" }
local REQUIRED_ABI = 2

-- ---------------------------------------------------------------- модуль
local bridge = nil
for _, name in ipairs( MOD_NAMES ) do
    pcall( require, name )
    local m = (package and package.loaded) and package.loaded[name]
    if type(m) == "table" and m.abi_version and m.abi_version() >= REQUIRED_ABI then
        bridge = m
        break
    end
end

if not bridge then
    print( "[d1control] нужен бинарный модуль d1bridge" )
    return
end

-- Открываем shared memory (идемпотентно — если уже открыто, ничего не делает).
-- Без этого bridge.read() возвращает nil и управление не работает.
if not bridge.open() then
    print( "[d1control] shared memory D1BridgeState недоступна " ..
           "(th43d.exe не запущен?) — управление не работает" )
else
    print( "[d1control] shared memory D1BridgeState открыта" )
end

-- ---------------------------------------------------------------- константы
local CELL = 64              -- размер клетки в 3D-мире (юниты GMod)

-- Направления TH4: код PCMD -> вектор в ГОРИЗОНТАЛЬНОЙ плоскости (X, Y).
-- Мир GMod Z-up: X = Col (восток), Y = Row (север), Z — высота.
-- Сдвиг в сетке (dRow, dCol) из changeRow/changeCol (Player.cpp:6051-6058):
--   1=UR( 0,-1) 2=UL(-1, 0) 3=DR(+1, 0) 4=DL( 0,+1)
--   5=U (-1,-1) 6=R (+1,-1) 7=D (+1,+1) 8=L (-1,+1)
-- Здесь X = dCol, Y = dRow.
local DIR_VECTORS = {
    [1] = { -1,  0 },
    [2] = {  0, -1 },
    [3] = {  0,  1 },
    [4] = {  1,  0 },
    [5] = { -1, -1 },
    [6] = { -1,  1 },
    [7] = {  1,  1 },
    [8] = {  1, -1 },
}
local DIR_NAMES = {
    [1] = "up-right", [2] = "up-left", [3] = "down-right", [4] = "down-left",
    [5] = "up", [6] = "right", [7] = "down", [8] = "left",
}

-- ---------------------------------------------------------------- обзор
--
-- Чтобы 3D-сцена ТОЧНО соответствовала изометрии TH4, камера должна стоять
-- в фиксированном ракурсе относительно сетки уровня:
--     yaw = 225°, pitch = +30° (смотрим вниз)
-- При такой ориентации:
--     "вперёд" (W) -> PCMD_5 (вверх по экрану TH4)
--     "вправо" (D) -> PCMD_6 (вправо по экрану TH4)
-- Проверено расчётом: 3D-проекция даёт ровно TH4-изометрию
-- px = (dRow-dCol)*64, py = (dRow+dCol)*32.
--
-- Мышь (mlook GMod) вращает камеру ОТНОСИТЕЛЬНО этого базового ракурса.
local TH4_BASE_YAW   = 225
local TH4_BASE_PITCH = 30

-- ---------------------------------------------------------------- состояние
-- Камера стартует в базовом TH4-ракурсе, чтобы 3D-сцена сразу выглядела
-- как изометрия TH4.
local camYaw    = TH4_BASE_YAW
local camPitch  = TH4_BASE_PITCH
local mouseSens = 0.2

local heroX, heroY, heroZ = 0, 0, 0
local heroRow, heroCol    = 0, 0
local heroCurAction = 0
local heroYaw   = 0
local targetYaw = 0
local isMoving  = false
local lastSentDir = nil
local captureMode = false
local mouseCaptured = false
local lastSendTime = 0
local sendCount = 0
local hookBroken = false

local targetYawFromPlayer = 0
local targetPitchFromPlayer = 0
local camYawOffset = 0
local camPitchOffset = 0
local refEyeYaw = nil      -- угол взгляда игрока в момент загрузки (база отсчёта)
local refEyePitch = nil

-- ---------------------------------------------------------------- логирование
-- API файлов GMod (проверено экспериментом):
--   file.Write(имя, содержимое)        — 2 аргумента, путь по умолчанию DATA
--   file.Open(имя, режим, путь)        — режим "a" дописывает
--   file.Append(имя, содержимое, путь) — порядок как у Write
--   io.* в клиенте ЗАБЛОКИРОВАНО (песочница) — не используем
--
-- Путь взят тот же, что у proven-рабочего bridge_cmd.json (data/d1bridge/).
local LOG_PATH = "d1bridge/d1control.log"
local LOG_ID   = "DATA"
local logLastState = ""
local logError = nil

-- Проверяем канал записи: пишем пробу и ждём, пока файл появится.
-- GMod пишет файлы ОТЛОЖЕННО, поэтому сразу после file.Write
-- file.Exists может вернуть false — проверяем с задержкой.
local function initLog()
    local ok, err = pcall( function()
        file.Write( LOG_PATH, "probe\n" )
    end )
    if not ok then
        logError = tostring( err )
        return false
    end
    return true
end

local logReady = initLog()

local function logLine( s )
    if not logReady then return end
    pcall( function()
        local f = file.Open( LOG_PATH, "a", LOG_ID )
        if f then
            f:Write( string.format( "[%.2f] %s\n", CurTime(), s ) )
            f:Close()
        end
    end )
end

-- ---------------------------------------------------------------- утилиты
-- Плавный поворот угла по кратчайшей дуге
local function lerpAngle( cur, target, maxStep )
    local diff = ( target - cur ) % 360
    if diff > 180 then diff = diff - 360 end
    if diff >  maxStep then diff =  maxStep end
    if diff < -maxStep then diff = -maxStep end
    return cur + diff
end

-- Yaw вектора (X, Y) в горизонтальной плоскости, конвенция GMod
local function yawOf( x, y )
    return math.deg( math.atan2( y, x ) )
end

-- Базис камеры в ГОРИЗОНТАЛЬНОЙ плоскости.
--
-- ВАЖНО: в GMod мир Z-up! X=восток, Y=север, Z=вверх.
-- Горизонтальная плоскость — XY, а компонента .z у вектора направления —
-- ВЕРТИКАЛЬНАЯ (при pitch=0 она всегда 0).
-- Раньше читалась f.z/r.z — из-за этого движение всегда было (±1, 0).
local function cameraBasis()
    local ang = Angle( 0, camYaw, 0 )
    local f = ang:Forward()
    local r = ang:Right()
    return f.x, f.y, r.x, r.y
end

-- Применить угол обзора: базовый ракурс TH4 + поворот мышью от него.
local function applyPlayerAngles()
    local yaw = TH4_BASE_YAW
    local pitch = TH4_BASE_PITCH

    -- Поворот мышью: разница между текущим углом взгляда игрока и тем,
    -- что было в момент загрузки.
    if refEyeYaw ~= nil then
        local d = ( targetYawFromPlayer - refEyeYaw ) % 360
        if d > 180 then d = d - 360 end
        yaw = yaw + d
        pitch = math.Clamp( pitch + ( targetPitchFromPlayer - refEyePitch ), -89, 89 )
    end

    yaw = yaw + camYawOffset
    pitch = math.Clamp( pitch + camPitchOffset, -89, 89 )

    camYaw = lerpAngle( camYaw, yaw, 25 )
    camPitch = pitch
end

-- ---------------------------------------------------------------- ввод
local function keyDown( inKey, physKey )
    return input.IsKeyDown( inKey ) or ( physKey and input.IsKeyDown( physKey ) )
end

local function getMoveVector()
    local fwd = 0
    local side = 0

    if keyDown( IN_FORWARD,  KEY_W ) then fwd  = fwd + 1 end
    if keyDown( IN_BACK,     KEY_S ) then fwd  = fwd - 1 end
    if keyDown( IN_MOVERIGHT, KEY_D ) then side = side + 1 end
    if keyDown( IN_MOVELEFT,  KEY_A ) then side = side - 1 end

    if fwd == 0 and side == 0 then return 0, 0 end

    -- Горизонтальный базис камеры: (forward.X, forward.Y) и (right.X, right.Y)
    local fx, fy, rx, ry = cameraBasis()
    local mx = fwd * fx + side * rx
    local my = fwd * fy + side * ry

    local len = math.sqrt( mx * mx + my * my )
    if len > 0 then mx, my = mx / len, my / len end
    return mx, my
end

-- Ближайшее из 8 направлений TH4 к вектору (mx, my) в квадратной сетке.
-- Направления идут через 45°, поэтому достаточно сравнить yaw.
local function pickDirection( mx, my )
    local want = yawOf( mx, my )
    local best, bestDiff = nil, 1e9
    for code, v in pairs( DIR_VECTORS ) do
        local d = math.abs( ( yawOf( v[1], v[2] ) - want + 540 ) % 360 - 180 )
        if d < bestDiff then
            bestDiff = d
            best = code
        end
    end
    return best
end

-- ---------------------------------------------------------------- мышь
-- input.GetMouseDelta в GMod-клиенте НЕТ (это серверная функция).
-- Но движок GMod сам поворачивает взгляд мышью (bind "+mlook").
--
-- ВАЖНО: у игрока GetAngles() возвращает угол ТЕЛА (следует за движением),
-- а EyeAngles() — угол ВЗГЛЯДА (следует за мышью). Для камеры нужен
-- именно взгляд, иначе возникает обратная связь: камера -> движение ->
-- угол тела -> камера, и всё схлопывается в одно направление.
local function updateMouse()
    local ply = Entity( 1 )
    if not ply or not ply:IsValid() then return end

    local ok, ang = pcall( function() return ply:EyeAngles() end )
    if not ok or not ang then
        ok, ang = pcall( function() return ply:GetAngles() end )
    end
    if not ok or not ang then return end

    targetYawFromPlayer = ang.y
    targetPitchFromPlayer = math.Clamp( ang.p, -89, 89 )

    -- Первый кадр: запоминаем ФАКТИЧЕСКИЙ угол взгляда как базу отсчёта.
    -- Важно: не пытаемся выставлять EyeAngles — движок их всё равно
    -- сбрасывает, и база отсчёта от этого «уплывает».
    -- Базовый ракурс камеры (225/30) отсчитывается отсюда, поэтому вид
    -- всё равно начинается с изометрии TH4.
    if refEyeYaw == nil then
        refEyeYaw = ang.y
        refEyePitch = math.Clamp( ang.p, -89, 89 )
    end
end

-- Захват курсора: input.EnableMouseCapture в GMod-клиенте отсутствует.
local function updateCapture()
    if not captureMode then return end
    if not mouseCaptured and input.EnableMouseCapture then
        mouseCaptured = true
        input.EnableMouseCapture( true )
    end
end

-- ---------------------------------------------------------------- обновление
local function update()
    local p = bridge.read()
    if not p then return end

    heroRow, heroCol = p.Row, p.Col
    -- Мир GMod Z-up: X=Col (восток), Y=Row (север), Z — высота
    heroX = heroCol * CELL
    heroY = heroRow * CELL
    heroZ = 0
    heroCurAction = p.CurAction or 0

    local mx, my = getMoveVector()

    -- Логируем только при смене состояния (чтобы лог не рос бесконечно)
    local state = string.format( "move=%.2f,%.2f dir=%s yaw=%.0f eye=%.0f",
        mx, my, tostring( pickDirection( mx, my ) ), camYaw, targetYawFromPlayer )
    if state ~= logLastState then
        logLastState = state
        logLine( string.format( "R%d C%d cur=%d | %s",
            heroRow, heroCol, heroCurAction, state ) )
    end

    if mx ~= 0 or my ~= 0 then
        isMoving = true

        -- Угол модели героя = направление движения в горизонтальной плоскости
        targetYaw = yawOf( mx, my )

        local dir = pickDirection( mx, my )
        if dir then
            local now = CurTime()
            -- Отправляем шаг, если направление изменилось ИЛИ герой дошагал
            -- (CurAction == 0) и клавиша всё ещё зажата.
            if dir ~= lastSentDir or ( heroCurAction == 0 and now - lastSendTime > 0.05 ) then
                if dir ~= lastSentDir then
                    local msg = string.format(
                        "dir=%d(%s) move=(%.2f,%.2f) yaw=%.0f eye=%.0f R%d C%d",
                        dir, DIR_NAMES[ dir ] or "?", mx, my, camYaw,
                        targetYawFromPlayer, heroRow, heroCol )
                    logLine( "  -> SEND " .. msg )
                    -- Дублируем в чат только если включён verbose-режим
                    -- (иначе чат засоряется при каждом шаге)
                    if d1Verbose then
                        chat.AddText( Color( 70, 200, 110 ), "[d1] ", Color( 230, 230, 235 ), msg )
                    end
                end
                lastSentDir = dir
                lastSendTime = now
                sendCount = sendCount + 1
                bridge.send_command( dir, 0, 0 )
            end
        end
    else
        isMoving = false
        lastSentDir = nil
    end

    heroYaw = lerpAngle( heroYaw, targetYaw, 12 )
end

-- ---------------------------------------------------------------- хуки
-- Think обёрнут в pcall: если функция недоступна в этом контексте,
-- ошибка не должна сыпаться сотни раз в секунду.
hook.Add( "Think", "d1control_update", function()
    if hookBroken then return end
    local ok, err = pcall( function()
        updateCapture()
        updateMouse()
        applyPlayerAngles()
        update()
    end )
    if not ok then
        hookBroken = true
        print( "[d1control] Think отключён из-за ошибки: " .. tostring( err ) )
    end
end )

-- ---------------------------------------------------------------- HUD-отладка
-- Рисуем состояние ввода прямо на экране — не зависит от записи файлов.
surface.CreateFont( "D1CTRL_Debug", {
    font = "Consolas", size = 15, weight = "BOLD", antialias = true,
} )

local dbgLines = {}
local dbgTimer = 0

local function updateDebugInfo()
    local mx, my = getMoveVector()
    local keys = {}
    if keyDown( IN_FORWARD, KEY_W )  then keys[#keys+1] = "W" end
    if keyDown( IN_BACK, KEY_S )     then keys[#keys+1] = "S" end
    if keyDown( IN_MOVERIGHT, KEY_D ) then keys[#keys+1] = "D" end
    if keyDown( IN_MOVELEFT, KEY_A )  then keys[#keys+1] = "A" end

    local fx, fy = cameraBasis()
    local dir = pickDirection( mx, my )

    dbgLines = {
        string.format( "keys=[%s] move=(%.2f,%.2f) dir=%s(%s)",
            table.concat( keys, "," ), mx, my, tostring( dir ),
            DIR_NAMES[ dir or 0 ] or "-" ),
        string.format( "yaw=%.0f eye=%.0f pitch=%.0f fwd=(%.2f,%.2f) heroYaw=%.0f",
            camYaw, targetYawFromPlayer, camPitch, fx, fy, heroYaw ),
        string.format( "R%d C%d cur=%d sent=%d log=%s",
            heroRow, heroCol, heroCurAction, sendCount,
            (logReady and "file" or "NONE") ),
    }
end

hook.Add( "HUDPaint", "d1control_debug", function()
    if not d1ShowDebug then return end
    updateDebugInfo()

    local x, y = 20, 200
    surface.SetDrawColor( 0, 0, 0, 170 )
    surface.DrawRect( x - 5, y - 5, 460, 60 )
    for i, line in ipairs( dbgLines ) do
        draw.SimpleText( line, "D1CTRL_Debug", x, y + ( i - 1 ) * 16,
            Color( 120, 255, 140 ), TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP )
    end
end )

-- ---------------------------------------------------------------- API
D1Control = {
    GetYaw       = function() return camYaw end,
    GetPitch     = function() return camPitch end,
    GetHeroYaw   = function() return heroYaw end,
    GetHeroPos   = function() return heroX, heroY, heroZ end,
    GetHeroCell  = function() return heroRow, heroCol end,
    IsMoving     = function() return isMoving end,
    GetDir       = function() return lastSentDir end,
    GetBasis     = cameraBasis,
}

-- ---------------------------------------------------------------- команды
-- Показать/скрыть отладочный HUD
d1ShowDebug = false
-- Подробный вывод в чат при каждой смене направления
d1Verbose = false
concommand.Add( "d1_debugshow", function()
    d1ShowDebug = not d1ShowDebug
    chat.AddText( Color( 70, 200, 110 ), "[d1control] отладка: ",
        Color( 230, 230, 235 ), d1ShowDebug and "показана" or "скрыта" )
end )

-- Подробный вывод в чат
concommand.Add( "d1_verbose", function()
    d1Verbose = not d1Verbose
    chat.AddText( Color( 70, 200, 110 ), "[d1control] подробный вывод: ",
        Color( 230, 230, 235 ), d1Verbose and "вкл" or "выкл" )
end )

concommand.Add( "d1_capture", function()
    captureMode = not captureMode
    chat.AddText( Color( 70, 200, 110 ), "[d1control] захват курсора: ",
        Color( 230, 230, 235 ),
        captureMode and "вкл" or "выкл (в GMod-клиенте недоступен)" )
end )

concommand.Add( "d1_turn", function( _, _, args )
    camYawOffset = camYawOffset + ( tonumber( args[1] ) or 0 )
    camPitchOffset = math.Clamp( camPitchOffset + ( tonumber( args[2] ) or 0 ), -89, 89 )
    chat.AddText( Color( 70, 200, 110 ), "[d1control] смещение обзора: yaw=" ..
        camYawOffset .. " pitch=" .. camPitchOffset )
end )

concommand.Add( "d1_reset", function()
    -- Вернуть камеру в базовый ракурс TH4 (yaw=225, pitch=30):
    -- сбрасываем смещения и переснимаем текущий угол взгляда как базу.
    camYawOffset = 0
    camPitchOffset = 0
    refEyeYaw = nil
    updateMouse()
    chat.AddText( Color( 70, 200, 110 ), "[d1control] обзор сброшен к TH4-ракурсу " ..
        "(yaw=225, pitch=30)" )
end )

concommand.Add( "d1_look", function()
    local fx, fy = cameraBasis()
    local rx, ry = (function()
        local r = Angle( 0, camYaw, 0 ):Right()
        return r.x, r.y
    end )()
    chat.AddText( Color( 70, 200, 110 ), "[d1control] " )
    chat.AddText( Color( 230, 230, 235 ), string.format(
        "yaw=%.0f (игрок %.0f) pitch=%.0f forward=(%.2f,%.2f) right=(%.2f,%.2f)",
        camYaw, targetYawFromPlayer, camPitch, fx, fy, rx, ry ) )
    chat.AddText( Color( 230, 230, 235 ), string.format(
        "heroYaw=%.0f dir=%s  | TH4-ракурс: yaw=225 -> forward=(-0.71,-0.71) right=(-0.71,0.71)",
        heroYaw, DIR_NAMES[ lastSentDir or 0 ] or "-" ) )
end )

-- Какие клавиши движения GMod видит нажатыми ПРЯМО СЕЙЧАС.
-- Позволяет проверить, работает ли привязка +forward/+back/+moveleft/+moveright.
concommand.Add( "d1_keys", function()
    local function st( inKey, physKey )
        local a = input.IsKeyDown( inKey )
        local b = physKey and input.IsKeyDown( physKey ) or false
        if a and b then return "IN+KEY" elseif a then return "IN" elseif b then return "KEY" end
        return "-"
    end
    local mx, my = getMoveVector()

    chat.AddText( Color( 70, 200, 110 ), "[d1keys] " )
    chat.AddText( Color( 230, 230, 235 ), string.format(
        "W=%s S=%s A=%s D=%s | move=(%.2f,%.2f) dir=%s",
        st( IN_FORWARD, KEY_W ), st( IN_BACK, KEY_S ),
        st( IN_MOVELEFT, KEY_A ), st( IN_MOVERIGHT, KEY_D ),
        mx, my, DIR_NAMES[ lastSentDir or 0 ] or "-" ) )
end )

-- Очистить лог
concommand.Add( "d1_logclear", function()
    pcall( function() file.Delete( LOG_PATH, LOG_ID ) end )
    logLastState = ""
    chat.AddText( Color( 70, 200, 110 ), "[d1control] лог очищен" )
end )

-- Сбросить смещение обзора (камера = взгляд игрока)
concommand.Add( "d1_lookreset", function()
    camYawOffset = 0
    camPitchOffset = 0
    chat.AddText( Color( 70, 200, 110 ), "[d1control] смещение обзора сброшено" )
end )

concommand.Add( "d1_debug", function()
    local fx, fy = cameraBasis()
    local mx, my = getMoveVector()
    local keys = {}
    if keyDown( IN_FORWARD, KEY_W )  then keys[#keys+1] = "W" end
    if keyDown( IN_BACK, KEY_S )     then keys[#keys+1] = "S" end
    if keyDown( IN_MOVERIGHT, KEY_D ) then keys[#keys+1] = "D" end
    if keyDown( IN_MOVELEFT, KEY_A )  then keys[#keys+1] = "A" end

    chat.AddText( Color( 70, 200, 110 ), "[d1debug] " )
    chat.AddText( Color( 230, 230, 235 ), string.format(
        "клавиши=[%s] move=(%.2f,%.2f) yaw=%.0f(игрок %.0f) fwd=(%.2f,%.2f) dir=%s команд=%d CurAction=%d",
        table.concat( keys, "," ), mx, my, camYaw, targetYawFromPlayer, fx, fy,
        DIR_NAMES[ lastSentDir or 0 ] or "-", sendCount, heroCurAction ) )
end )

-- ВНИМАНИЕ: лог НЕ удаляем при загрузке!
-- GMod пишет файлы отложенно, поэтому file.Delete после file.Write
-- удаляет уже записанное (файл не появлялся вообще).
-- Очистка — только вручную командой d1_logclear.
logReady = initLog()
logLastState = ""
camYawOffset = 0
camPitchOffset = 0

-- Стартовая запись — сразу видно, работает ли канал записи
logLine( "=== d1control загружен ===" )
logLine( string.format( "модуль: %s, open=%s",
    tostring( bridge.abi_version and bridge.abi_version() or "?" ),
    tostring( bridge.is_open and bridge.is_open() ) ) )

print( "[d1control] FPS-управление: WASD относительно камеры, мышь — обзор" )
print( "[d1control] лог: " .. (logReady and "garrysmod/data/" .. LOG_PATH
    or ("НЕ РАБОТАЕТ (" .. tostring( logError ) .. ") — смотри чат") ) )
