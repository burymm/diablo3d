-- d1meshprobe3.lua — что вообще есть в render/cam и работает ли CalcView.
-- Запуск: lua_openscript_cl "autorun/client/d1meshprobe3.lua"

print( "=== d1meshprobe3 ===" )

print( "GAMEMODE_NAME = " .. tostring( GAMEMODE_NAME ) )

local function dump( name, tbl )
    local keys = {}
    for k, v in pairs( tbl ) do
        keys[#keys+1] = k .. "(" .. type( v ) .. ")"
    end
    table.sort( keys )
    print( name .. " (" .. tostring( #keys ) .. "): " .. table.concat( keys, ", " ) )
end

dump( "render", render )
dump( "cam", cam )
dump( "surface", surface )

-- Хуки камеры
local ht = hook.GetTable()
for _, h in ipairs( { "CalcView", "PreDraw", "PostDraw", "Think", "HUDPaint",
                      "CalcPostView", "RenderScreenshots" } ) do
    print( "  hook " .. h .. ": " .. tostring( ht[h] ~= nil ) )
end

-- Методы игрока, влияющие на камеру
local ply = Entity( 1 )
if ply and ply:IsValid() then
    for _, m in ipairs( { "SetViewPunch", "SetEyeAngles", "SetAngles", "SetFOV",
                          "SetPos", "GetAngles", "EyeAngles", "GetForward" } ) do
        print( "  ply." .. m .. " = " .. type( ply[m] ) )
    end
end

-- Проверяем, вызывается ли хук CalcView
local called = 0
hook.Add( "CalcView", "d1probe3_calcview", function()
    called = called + 1
    if called == 1 then
        print( "  CalcView ВЫЗВАН" )
    end
    if called == 30 then
        print( "  CalcView вызван 30+ раз" )
    end
end )

print( "=== d1meshprobe3 done (ждём 2 секунды, потом d1probe3_status) ===" )

concommand.Add( "d1probe3_status", function()
    print( "[d1probe3] CalcView вызван " .. called .. " раз" )
end )
