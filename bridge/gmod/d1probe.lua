-- d1probe.lua — безопасный зонд: что реально доступно в GMod-клиенте
-- Запуск: lua_openscript_cl "autorun/client/d1probe.lua"

local function keys( t )
    local out = {}
    if type( t ) ~= "table" then return "<не таблица: " .. type( t ) .. ">" end
    for k, v in pairs( t ) do
        out[#out+1] = tostring( k ) .. "(" .. type( v ) .. ")"
    end
    table.sort( out )
    return table.concat( out, ", " )
end

print( "=== d1probe ===" )

-- 1. Все ключи input
print( "input: " .. keys( input ) )

-- 2. Есть ли Lua-обёртки для мыши
for _, name in ipairs( { "GetMouseDelta", "EnableMouseCapture", "GetCursorPos",
                         "SetCursorPos", "LookAt", "LookUp", "LookDown",
                         "GetMouseX", "GetMouseY", "SetMouseX", "SetMouseY" } ) do
    local ok, val = pcall( function() return input[ name ] end )
    print( string.format( "  input.%-20s = %s", name, ok and tostring( val ) or "ERR" ) )
end

-- 3. Доступен ли локальный игрок
local ply = Entity( 1 )
print( "Entity(1) = " .. tostring( ply ) .. " valid=" .. tostring( ply and ply:IsValid() ) )
if ply and ply:IsValid() then
    local ok, ang = pcall( function() return ply:GetAngles() end )
    print( "  angles = " .. tostring( ok and ang or "ERR" ) )
    local ok2, eye = pcall( function() return ply:EyeAngles() end )
    print( "  eyeAngles = " .. tostring( ok2 and eye or "ERR" ) )
end
print( "LocalPlayer() = " .. tostring( LocalPlayer and LocalPlayer() ) )

-- 4. Есть ли хук CalcView (переопределение камеры)
print( "hook.GetTable() has CalcView = " ..
    tostring( hook.GetTable and hook.GetTable()["CalcView"] and "yes" or "no" ) )

print( "=== probe done ===" )
