-- d1meshprobe2.lua — точные сигнатуры immediate-mode API мешей GMod.
-- Запуск: lua_openscript_cl "autorun/client/d1meshprobe2.lua"

print( "=== d1meshprobe2 ===" )

-- ------------------------------------------------------------------ сигнатуры
-- Вызываем каждую функцию со строкой вместо аргументов: Lua сообщает
-- ожидаемый тип -> восстанавливаем сигнатуру.
local names = { "Begin", "End", "Color", "Normal", "Position", "Quad", "QuadEasy",
                "TexCoord", "TangentT", "TangentS", "Specular", "AdvanceVertex",
                "VertexCount", "BoneData", "UserData" }

for _, n in ipairs( names ) do
    local f = mesh[ n ]
    if type( f ) ~= "function" then
        print( string.format( "  %-14s = %s", n, type( f ) ) )
    else
        local parts = {}
        for i = 1, 6 do
            local args = {}
            for j = 1, i do args[j] = "??" end
            local ok, err = pcall( f, unpack( args ) )
            if ok then
                parts[#parts+1] = i .. ":ok"
                break
            else
                local t = string.match( tostring( err ), "%((.-)%)" )
                parts[#parts+1] = i .. ":" .. ( t or "?" )
            end
        end
        print( string.format( "  %-14s %s", n, table.concat( parts, "  " ) ) )
    end
end

-- ------------------------------------------------------------------ пробы вызова
local function t( name, fn )
    local ok, err = pcall( fn )
    print( string.format( "  %-42s ok=%-5s %s", name, tostring( ok ),
        ok and "" or tostring( err ) ) )
    return ok
end

print( "--- вызовы ---" )

t( "Begin(4,6,'Debug/DebugMaterial')", function()
    mesh.Begin( 4, 6, "Debug/DebugMaterial" )
end )
t( "Begin(4,6)", function()
    mesh.Begin( 4, 6 )
end )
t( "Begin(4)", function()
    mesh.Begin( 4 )
end )
t( "Begin(4,6,Material())", function()
    mesh.Begin( 4, 6, Material( "Debug/DebugMaterial" ) )
end )

t( "Position(0,0,0)", function() mesh.Position( 0, 0, 0 ) end )
t( "Position(Vector)", function() mesh.Position( Vector( 0, 0, 0 ) ) end )
t( "Color(255,0,0,255)", function() mesh.Color( 255, 0, 0, 255 ) end )
t( "Color(Color())", function() mesh.Color( Color( 255, 0, 0 ) ) end )
t( "TexCoord(0,0)", function() mesh.TexCoord( 0, 0 ) end )
t( "Normal(0,0,1)", function() mesh.Normal( 0, 0, 1 ) end )
t( "Normal(Vector)", function() mesh.Normal( Vector( 0, 0, 1 ) ) end )
t( "AdvanceVertex()", function() mesh.AdvanceVertex() end )
t( "VertexCount()", function() print( "    vertexCount=" .. tostring( mesh.VertexCount() ) ) end )
t( "Quad()", function() mesh.Quad() end )
t( "Quad(4xVector)", function()
    mesh.Quad( Vector( 0, 0, 0 ), Vector( 1, 0, 0 ), Vector( 1, 1, 0 ), Vector( 0, 1, 0 ) )
end )
t( "QuadEasy(4xVector)", function()
    mesh.QuadEasy( Vector( 0, 0, 0 ), Vector( 1, 0, 0 ), Vector( 1, 1, 0 ), Vector( 0, 1, 0 ) )
end )
t( "QuadEasy(table,4)", function()
    mesh.QuadEasy( { Vector( 0, 0, 0 ), Vector( 1, 0, 0 ), Vector( 1, 1, 0 ), Vector( 0, 1, 0 ) }, 4 )
end )

-- ------------------------------------------------------------------ реальный квад
print( "--- рисуем квад 400x400 в начале координат ---" )
local drew = t( "Begin+QuadEasy+End", function()
    mesh.Begin( 4, 6, "Debug/DebugMaterial" )
    mesh.QuadEasy( Vector( 0, 0, 0 ), Vector( 400, 0, 0 ),
                   Vector( 400, 400, 0 ), Vector( 0, 400, 0 ) )
    mesh.End()
end )

if not drew then
    t( "Begin+Position*4+Quad+End", function()
        mesh.Begin( 4, 6, "Debug/DebugMaterial" )
        mesh.Position( 0, 0, 0 )     mesh.AdvanceVertex()
        mesh.Position( 400, 0, 0 )   mesh.AdvanceVertex()
        mesh.Position( 400, 400, 0 ) mesh.AdvanceVertex()
        mesh.Position( 0, 400, 0 )   mesh.AdvanceVertex()
        mesh.Quad()
        mesh.End()
    end )
end

-- Цветной квад (через SetColorMaterial + Begin без материала)
t( "SetColorMaterial+Begin(4,6)+QuadEasy", function()
    render.SetColorMaterial( Color( 255, 90, 0, 255 ) )
    mesh.Begin( 4, 6 )
    mesh.QuadEasy( Vector( -400, 0, 0 ), Vector( 0, 0, 0 ),
                   Vector( 0, 400, 0 ), Vector( -400, 400, 0 ) )
    mesh.End()
end )

print( "=== d1meshprobe2 done ===" )
