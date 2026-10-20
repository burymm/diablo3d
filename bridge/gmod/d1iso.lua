--[[--------------------------------------------------------------------------
    d1iso.lua  —  2D-изометрия уровня TH4 поверх экрана (GMod)

    Почему 2D: в этой сборке GMod не работают ни render.OverrideView*, ни
    surface.DrawPoly, ни PreDraw/HUDPaint/CalcView (проверено переписями
    render/hook). Работают: DrawRect, DrawTexturedRectRotated,
    DrawTexturedRectUV, DrawOverlay.

    Поэтому рисуем изометрию сам: генерируем TGA-атлас с ромбом плитки и
    гранями стены, грузим его как материал и раскладываем по экрану
    текстурированными прямоугольниками.

    Геометрия
    ---------
    Ортографическая проекция камеры GMod (Z-up):
        right = ( sin yaw, -cos yaw, 0 )
        up    = ( cos yaw*sin pitch, sin yaw*sin pitch, cos pitch )
        screen_x      = (P · right) * k
        screen_y_down = -(P · up) * k

    При yaw = 225°, pitch = +30° и k = 90.51/CELL это даёт РОВНО
    изометрию TH4:
        px = (dRow - dCol) * 64
        py = (dRow + dCol) * 32

    Данные уровня — настоящие (FineMap / TileBlockWalking из shared memory).

    Команды:
        d1iso_toggle   — показать/скрыть
        d1iso_info     — инфо
        d1iso_bg 0|1   — перекрывать ли фон
        d1iso_px [n]   — размер клетки на экране
--------------------------------------------------------------------------]]

-- ---------------------------------------------------------------- модуль
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
    print( "[d1iso] нужен бинарный модуль d1bridge с read_map_area" )
    return
end

-- ---------------------------------------------------------------- константы
local CELL    = 64      -- размер клетки в мире
local PX      = 64      -- пикселей на шаг сетки по экрану (как в TH4)
local WALL_H  = 46      -- высота стены на экране
local RADIUS  = 26      -- радиус читаемой области
local REFRESH = 0.3

-- Размеры фигур атласа
local TEX_W, TEX_H = 256, 160
local DIA_W, DIA_H = 128, 64          -- ромб плитки (диагонали)
local FACE_W = 64                    -- ширина грани стены
local FACE_H = 32 + WALL_H           -- высота грани стены (32 — скос клетки)

local K = 90.51 / CELL

-- ---------------------------------------------------------------- атлас (TGA)
-- Рисуем белым: цвет задаётся через surface.SetDrawColor (умножается).
local function buildAtlas()
    local rows = {}
    for y = 0, TEX_H - 1 do
        local bytes = {}
        for x = 0, TEX_W - 1 do
            local a = 0
            -- Ромб плитки: (0,0)-(128,64), диагонали 128 и 64
            if x < DIA_W and y < DIA_H then
                local cx, cy = DIA_W / 2, DIA_H / 2
                if math.abs( x - cx ) / ( DIA_W / 2 ) +
                   math.abs( y - cy ) / ( DIA_H / 2 ) <= 1 then
                    a = 255
                end
            end
            -- Грань стены +Col: (0,64)-(64,142). Скос 45°, бок вертикальный.
            if x < FACE_W and y >= 64 and y < 64 + FACE_H then
                local ly = y - 64
                local slant = x / 2            -- верхняя скосая кромка
                local bottom = slant + WALL_H  -- нижняя скосая кромка
                if ly >= slant and ly <= bottom then a = 255 end
            end
            -- Грань стены +Row: (64,64)-(128,142) — зеркальная.
            if x >= FACE_W and x < FACE_W * 2 and y >= 64 and y < 64 + FACE_H then
                local lx = x - FACE_W
                local ly = y - 64
                local slant = ( FACE_W - lx ) / 2
                local bottom = slant + WALL_H
                if ly >= slant and ly <= bottom then a = 255 end
            end
            bytes[#bytes+1] = string.char( 255, 255, 255, a )
        end
        rows[y+1] = table.concat( bytes )
    end

    -- Заголовок TGA (32 бита, альфа, начало сверху)
    local function w16( v ) return string.char( v % 256, math.floor( v / 256 ) ) end
    local hdr = string.char( 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0 ) ..
                w16( TEX_W ) .. w16( TEX_H ) .. string.char( 32, 40 )
    return hdr .. table.concat( rows )
end

-- ---------------------------------------------------------------- PNG
-- TGA может не подхватиться материальной системой. PNG надёжнее:
-- zlib-поток собираем из «stored» блоков (без сжатия), CRC32 — таблицей.
local CRC_T = nil

local function crcTable()
    if CRC_T then return CRC_T end
    CRC_T = {}
    for n = 0, 255 do
        local c = n
        for _ = 1, 8 do
            if c % 2 == 1 then
                c = bit.bxor( 0xEDB88320, math.floor( c / 2 ) )
            else
                c = math.floor( c / 2 )
            end
        end
        CRC_T[n] = c
    end
    return CRC_T
end

local function crc32( s )
    local t = crcTable()
    local c = 0xFFFFFFFF
    for i = 1, #s do
        local idx = bit.band( bit.bxor( c, s:byte( i ) ), 0xFF )
        c = bit.bxor( t[idx], bit.rshift( c, 8 ) )
    end
    return bit.bxor( c, 0xFFFFFFFF )
end

local function w32( v )
    v = v % 4294967296
    return string.char( v % 256, math.floor( v / 256 ) % 256,
        math.floor( v / 65536 ) % 256, math.floor( v / 16777216 ) % 256 )
end

local function adler32( s )
    local a, b = 1, 0
    for i = 1, #s do
        a = ( a + s:byte( i ) ) % 65521
        b = ( b + a ) % 65521
    end
    return b * 65536 + a
end

-- raw — «сырые» данные (каждый ряд уже с префиксом фильтра)
local function zlibStore( raw )
    local out = { string.char( 0x78, 0x01 ) }
    local pos, total = 1, #raw
    while pos <= total do
        local len = total - pos + 1
        if len > 65535 then len = 65535 end
        local last = 0
        if pos + len - 1 >= total then last = 1 end
        local nlen = 65535 - len
        out[#out+1] = string.char( last )
        out[#out+1] = string.char( len % 256, math.floor( len / 256 ) )
        out[#out+1] = string.char( nlen % 256, math.floor( nlen / 256 ) )
        out[#out+1] = string.sub( raw, pos, pos + len - 1 )
        pos = pos + len
    end
    out[#out+1] = w32( adler32( raw ) )
    return table.concat( out )
end

local function pngChunk( type_, data )
    local t = type_ .. data
    return w32( #data ) .. t .. w32( crc32( t ) )
end

-- rgba — плоский массив байт RGBA (W*H*4)
local function makePNG( W, H, rgba )
    -- ряды с префиксом фильтра 0
    local rows = {}
    for y = 0, H - 1 do
        rows[y+1] = string.char( 0 ) .. string.sub( rgba,
            y * W * 4 + 1, ( y + 1 ) * W * 4 )
    end
    local raw = table.concat( rows )

    local ihdr = w32( W ) .. w32( H ) .. string.char( 8, 6, 0, 0, 0 )
    return string.char( 137, 80, 78, 71, 13, 10, 26, 10 ) ..
           pngChunk( "IHDR", ihdr ) ..
           pngChunk( "IDAT", zlibStore( raw ) ) ..
           pngChunk( "IEND", "" )
end

local atlasMat = nil

-- Пиксели атласа: белые с альфой по форме фигур
local function buildAtlasPixels()
    local px = {}
    for i = 1, TEX_W * TEX_H * 4 do px[i] = 255 end

    local function set( x, y, a )
        if x < 0 or y < 0 or x >= TEX_W or y >= TEX_H then return end
        local idx = ( y * TEX_W + x ) * 4 + 1
        px[idx+3] = a
    end

    -- Ромб плитки: (0,0)-(128,64), диагонали 128 и 64
    local cx, cy = DIA_W / 2, DIA_H / 2
    for y = 0, DIA_H - 1 do
        for x = 0, DIA_W - 1 do
            if math.abs( x - cx ) / ( DIA_W / 2 ) +
               math.abs( y - cy ) / ( DIA_H / 2 ) <= 1 then
                set( x, y, 255 )
            end
        end
    end

    -- Грань стены +Col: (0,64)-(64,142): скос 45°, бок вертикальный
    for y = 64, 64 + FACE_H - 1 do
        for x = 0, FACE_W - 1 do
            local ly = y - 64
            local slant = x / 2
            if ly >= slant and ly <= slant + WALL_H then set( x, y, 255 ) end
        end
    end

    -- Грань стены +Row: (64,64)-(128,142) — зеркальная
    for y = 64, 64 + FACE_H - 1 do
        for x = FACE_W, FACE_W * 2 - 1 do
            local lx = x - FACE_W
            local ly = y - 64
            local slant = ( FACE_W - lx ) / 2
            if ly >= slant and ly <= slant + WALL_H then set( x, y, 255 ) end
        end
    end

    return px
end

local function loadAtlas()
    if atlasMat then return atlasMat end

    local png = makePNG( TEX_W, TEX_H, buildAtlasPixels() )
    print( "[d1iso] PNG-атлас: " .. #png .. " байт" )

    local paths = {
        { file = "materials/d1bridge/d1iso.png", path = "GAME",
          mat  = "materials/d1bridge/d1iso.png" },
        { file = "materials/d1bridge/d1iso.png", path = nil,
          mat  = "materials/d1bridge/d1iso.png" },
        { file = "d1bridge/d1iso.png", path = "DATA",
          mat  = "data/d1bridge/d1iso.png" },
        { file = "d1bridge/d1iso.png", path = nil,
          mat  = "d1bridge/d1iso.png" },
    }

    for _, p in ipairs( paths ) do
        local wrote = false
        pcall( function()
            if p.path == "GAME" then
                pcall( function() file.CreateDir( "materials/d1bridge", "GAME" ) end )
            elseif p.path == "DATA" then
                pcall( function() file.CreateDir( "d1bridge", "DATA" ) end )
            end
            if p.path then
                file.Write( p.file, png, p.path )
            else
                file.Write( p.file, png )
            end
            wrote = true
        end )
        print( string.format( "  %s [%s]: запись=%s exists=%s",
            p.mat, tostring( p.path ), tostring( wrote ),
            tostring( file.Exists( p.file, p.path ) ) ) )

        local m = Material( p.mat )
        local err = ( m and m:IsError() ) and "ОШИБКА" or "ок"
        print( string.format( "    material(%s) -> %s, %s",
            p.mat, err, ( m and m:GetName() ) or "nil" ) )

        if m and not m:IsError() then
            atlasMat = m
            print( "[d1iso] атлас загружен: " .. p.mat )
            return atlasMat
        end
    end

    print( "[d1iso] НЕ УДАЛОСЬ загрузить атлас — будет грубая отрисовка" )
    return nil
end

-- ---------------------------------------------------------------- состояние
-- По умолчанию выключено: 3D-сцена (d1scene.lua) рисует уровень сам,
-- а чёрный фон 2D-изометрии перекрыл бы его.
-- Включается командой d1iso_toggle.
local enabled = false
local bgSolid = true
local mapData = nil
local heroRow, heroCol = 0, 0
local heroX, heroY = 0, 0
local heroYaw = 0
local builtFor = nil

local nCells = 0
local cWorldX, cWorldY, cTile, cWall, cDepth = {}, {}, {}, {}, {}

-- Глубина для сортировки (от дальних к ближним)
local buckets = {}
for i = 1, 64 do buckets[i] = {} end
local NB = 64

-- ---------------------------------------------------------------- чтение карты
local function refresh()
    if not bridge or not bridge.read then return end
    local p = bridge.read()
    if not p then return end

    heroRow, heroCol = p.Row, p.Col
    heroX = heroCol * CELL
    heroY = heroRow * CELL
    if D1Control then heroYaw = D1Control.GetHeroYaw() end

    local area = bridge.read_map_area( p.Row, p.Col, RADIUS )
    if not area then return end

    local key = string.format( "%d:%d:%d:%d", area.origin_row, area.origin_col,
        area.w, area.h )
    if key == builtFor then return end
    builtFor = key
    mapData = area

    local tiles = area.tiles
    local walls = area.walls
    local w = area.w
    local h = area.h
    local oRow = area.origin_row
    local oCol = area.origin_col

    nCells = 0
    for dr = 0, h - 1 do
        for dc = 0, w - 1 do
            local idx = dr * w + dc + 1
            local tile = tiles[idx] or 0
            if tile ~= 0 then
                nCells = nCells + 1
                cWorldX[nCells] = ( oCol + dc ) * CELL
                cWorldY[nCells] = ( oRow + dr ) * CELL
                cTile[nCells] = tile
                cWall[nCells] = ( walls[idx] or 0 ) == 1 and 1 or 0
            end
        end
    end
end

-- ---------------------------------------------------------------- проекция
local yaw, pitch = 225, 30
local rx, ry = 0, 0
local ux, uy = 0, 0
local fx, fy = 0, 0
local originX, originY = 0, 0

local function updateCamera()
    if D1Control then
        yaw   = D1Control.GetYaw()
        pitch = D1Control.GetPitch()
    end
    local ra = math.rad( yaw )
    local rp = math.rad( pitch )
    local sY, cY = math.sin( ra ), math.cos( ra )
    local sP, cP = math.sin( rp ), math.cos( rp )

    rx = sY        ry = -cY
    ux = cY * sP   uy = sY * sP
    fx = cY * cP   fy = sY * cP

    originX = ScrW() * 0.5
    originY = ScrH() * 0.5
end

local function proj( wx, wy )
    local dx = wx - heroX
    local dy = wy - heroY
    return ( dx * rx + dy * ry ) * K + originX,
           -( dx * ux + dy * uy ) * K + originY
end

-- ---------------------------------------------------------------- сортировка
local function sortCells()
    local minD, maxD
    for i = 1, nCells do
        local dx = cWorldX[i] - heroX
        local dy = cWorldY[i] - heroY
        local d = dx * fx + dy * fy
        cDepth[i] = d
        if not minD or d < minD then minD = d end
        if not maxD or d > maxD then maxD = d end
    end
    if not minD then return end
    local span = maxD - minD
    if span <= 0 then span = 1 end

    for i = 1, NB do buckets[i] = {} end
    for i = 1, nCells do
        local b = math.floor( ( maxD - cDepth[i] ) / span * ( NB - 1 ) ) + 1
        if b < 1 then b = 1 elseif b > NB then b = NB end
        local list = buckets[b]
        list[#list+1] = i
    end
end

-- ---------------------------------------------------------------- отрисовка
local FLOOR_COLORS = {
    { 118, 108,  92 },
    { 132, 118,  96 },
    { 104, 104, 100 },
    { 142, 126, 100 },
    {  96,  92,  88 },
}

-- UV-координаты атласа (нормализованные)
local UV_DIA   = "0 0 " .. ( DIA_W / TEX_W ) .. " " .. ( DIA_H / TEX_H )
local UV_FACE1 = "0 " .. ( 64 / TEX_H ) .. " " .. ( FACE_W / TEX_W ) .. " " ..
                 ( ( 64 + FACE_H ) / TEX_H )
local UV_FACE2 = ( FACE_W / TEX_W ) .. " " .. ( 64 / TEX_H ) .. " " ..
                 ( FACE_W * 2 / TEX_W ) .. " " .. ( ( 64 + FACE_H ) / TEX_H )

local function drawCell( i )
    local x = cWorldX[i]
    local y = cWorldY[i]
    local ax, ay = proj( x, y )        -- левый верхний угол ромба

    if atlasMat then
        if cWall[i] == 1 then
            -- Две видимые грани + верх
            surface.SetDrawColor( 52, 48, 44, 255 )
            surface.DrawTexturedRectUV( ax - FACE_W, ay - WALL_H, FACE_W, FACE_H, UV_FACE1 )
            surface.SetDrawColor( 68, 63, 58, 255 )
            surface.DrawTexturedRectUV( ax, ay - WALL_H, FACE_W, FACE_H, UV_FACE2 )
            surface.SetDrawColor( 104, 97, 87, 255 )
            surface.DrawTexturedRectUV( ax, ay - WALL_H, DIA_W, DIA_H, UV_DIA )
        else
            local col = FLOOR_COLORS[ ( cTile[i] % 5 ) + 1 ]
            surface.SetDrawColor( col[1], col[2], col[3], 255 )
            surface.DrawTexturedRectUV( ax, ay, DIA_W, DIA_H, UV_DIA )
        end
    else
        -- Грубая отрисовка, если атлас не загрузился
        if cWall[i] == 1 then
            surface.SetDrawColor( 70, 65, 60, 255 )
            surface.DrawRect( ax - FACE_W, ay - WALL_H, FACE_W * 2, FACE_H )
        else
            local col = FLOOR_COLORS[ ( cTile[i] % 5 ) + 1 ]
            surface.SetDrawColor( col[1], col[2], col[3], 255 )
            surface.DrawRect( ax - FACE_W / 2, ay - DIA_H / 2, FACE_W, DIA_H )
        end
    end
end

local function drawHero()
    local ax, ay = proj( heroX, heroY )
    if atlasMat then
        -- Ромб героя — тот же атлас, но втрое меньше
        surface.SetDrawColor( 205, 65, 65, 255 )
        surface.DrawTexturedRectUV( ax - DIA_W * 0.3, ay - DIA_H * 0.3,
            DIA_W * 0.6, DIA_H * 0.6, UV_DIA )
    else
        surface.SetDrawColor( 205, 65, 65, 255 )
        surface.DrawRect( ax - 18, ay - 9, 36, 18 )
    end

    -- Носок
    local rad = math.rad( heroYaw )
    local fxw, fyw = math.cos( rad ), math.sin( rad )
    local nx, ny = proj( heroX + fxw * CELL * 0.8, heroY + fyw * CELL * 0.8 )
    surface.SetDrawColor( 255, 220, 90, 255 )
    surface.DrawRect( nx - 6, ny - 4, 12, 8 )
end

-- ---------------------------------------------------------------- кадр
local drawCount = 0

local function drawOverlay()
    if not enabled or not mapData then return end

    updateCamera()
    sortCells()

    if bgSolid then
        surface.SetDrawColor( 16, 16, 20, 255 )
        surface.DrawRect( 0, 0, ScrW(), ScrH() )
    end

    if atlasMat then surface.SetTexture( atlasMat ) end

    local W, H = ScrW(), ScrH()
    local drawn = 0

    for b = 1, NB do
        local list = buckets[b]
        for k = 1, #list do
            local i = list[k]
            local cx, cy = proj( cWorldX[i], cWorldY[i] )
            if cx > -DIA_W and cx < W + DIA_W and cy > -DIA_H and cy < H + DIA_H then
                drawCell( i )
                drawn = drawn + 1
            end
        end
    end

    drawHero()
    drawCount = drawn
end

-- ---------------------------------------------------------------- инициализация
refresh()
loadAtlas()
timer.Create( "d1iso_refresh", REFRESH, 0, refresh )

hook.Add( "DrawOverlay", "d1iso_draw", function()
    drawOverlay()
end )

-- ---------------------------------------------------------------- команды
concommand.Add( "d1iso_toggle", function()
    enabled = not enabled
    chat.AddText( Color( 70, 200, 110 ), "[d1iso] ",
        Color( 230, 230, 235 ), enabled and "изометрия включена" or "изометрия выключена" )
end )

concommand.Add( "d1iso_bg", function( _, _, args )
    bgSolid = ( tonumber( args[1] ) or 1 ) ~= 0
    chat.AddText( Color( 70, 200, 110 ), "[d1iso] фон: " .. ( bgSolid and "да" or "нет" ) )
end )

concommand.Add( "d1iso_px", function( _, _, args )
    PX = math.Clamp( tonumber( args[1] ) or PX, 16, 160 )
    K = 90.51 / CELL * ( PX / 64 )
    chat.AddText( Color( 70, 200, 110 ), "[d1iso] размер клетки: " .. PX .. " px" )
end )

concommand.Add( "d1iso_info", function()
    chat.AddText( Color( 70, 200, 110 ), "[d1iso] " )
    chat.AddText( Color( 230, 230, 235 ), string.format(
        "клеток=%d нарисовано=%d атлас=%s герой R%d C%d yaw=%.0f pitch=%.0f px=%d",
        nCells, drawCount, atlasMat and "есть" or "НЕТ", heroRow, heroCol,
        yaw, pitch, PX ) )
end )

-- ---------------------------------------------------------------- API
D1Iso = {
    Disable = function() enabled = false end,
    Enable  = function() enabled = true end,
    SetBg   = function( v ) bgSolid = v and true or false end,
    GetInfo = function()
        return nCells, drawCount, heroRow, heroCol, yaw, pitch, PX
    end,
}

print( "[d1iso] 2D-изометрия уровня TH4 загружена. " ..
       "Команды: d1iso_toggle, d1iso_info, d1iso_bg, d1iso_px" )
