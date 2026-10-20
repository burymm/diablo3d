-- d1renderprobe.lua — проверяем, рисует ли IMesh и работает ли cam.Start3D.
-- Запуск: lua_openscript_cl "autorun/client/d1renderprobe.lua"
--
-- ВАЖНО: снимаем старый хук, если он остался от прошлой загрузки —
-- иначе он будет сыпать ошибками каждый кадр.
-- hook.Remove принимает (событие, идентификатор).
hook.Remove( "RenderScene", "d1renderprobe" )

-- Дальше зонд ничего не рисует: свою задачу (проверка IMesh + cam.Start3D)
-- он выполнил — IMesh рисует, cam.Start3D работает.
local function cube( cx, cy, cz, h, r, g, b )
    -- 6 граней куба
    local x0, x1 = cx - h, cx + h
    local y0, y1 = cy - h, cy + h
    local z0, z1 = cz - h, cz + h
    local v = {
        { x0,y0,z0 }, { x1,y0,z0 }, { x1,y1,z0 }, { x0,y1,z0 },
        { x0,y0,z1 }, { x1,y0,z1 }, { x1,y1,z1 }, { x0,y1,z1 },
    }
    local faces = {
        { 1,2,3,4 }, { 5,8,7,6 }, { 1,5,6,2 },
        { 2,6,7,3 }, { 3,7,8,4 }, { 4,8,5,1 },
    }
    -- ВАЖНО: первый аргумент mesh.Begin — ТИП ПРИМИТИВА (0..7),
    -- второй — количество ВЕРШИН (максимум 32768).
    mesh.Begin( 0, 24, "Debug/DebugMaterial" )
    mesh.Color( r, g, b, 255 )
    for _, f in ipairs( faces ) do
        local a, b2, c, d = v[f[1]], v[f[2]], v[f[3]], v[f[4]]
        local ux, uy, uz = b2[1]-a[1], b2[2]-a[2], b2[3]-a[3]
        local wx, wy, wz = c[1]-a[1], c[2]-a[2], c[3]-a[3]
        local nx = uy*wz - uz*wy
        local ny = uz*wx - ux*wz
        local nz = ux*wy - uy*vx
        local l = math.sqrt( nx*nx + ny*ny + nz*nz )
        if l > 0 then nx, ny, nz = nx/l, ny/l, nz/l end
        mesh.Normal( nx, ny, nz )
        mesh.Quad( a, b2, c, d )
    end
    mesh.End()
end

hook.Add( "RenderScene", "d1renderprobe", function()
    -- намеренно пусто: кубы больше не нужны
end )

print( "=== d1renderprobe ===" )
print( "Перед вами должен появиться куб у ваших ног." )
print( "КРАСНЫЙ = обычный IMesh (работает ли рендер вообще?)" )
print( "ЗЕЛЁНЫЙ = IMesh внутри cam.Start3D + IgnoreZ" )
print( "Если зелёный перекрыл красный — cam.Start3D работает." )
print( "=== d1renderprobe done ===" )
