-- d1meshprobe4.lua — семантика mesh.Begin: тип примитива и смысл count.
-- Запуск: lua_openscript_cl "autorun/client/d1meshprobe4.lua"

print( "=== d1meshprobe4 ===" )

local v1 = Vector( 0, 0, 0 )
local v2 = Vector( 1, 0, 0 )
local v3 = Vector( 1, 1, 0 )
local v4 = Vector( 0, 1, 0 )

local function t( name, fn )
    local ok, err = pcall( fn )
    pcall( function() mesh.End() end )
    print( string.format( "  %-30s ok=%-5s %s", name, tostring( ok ),
        ok and "" or tostring( err ) ) )
    return ok
end

print( "--- какой тип примитива валиден (count=100) ---" )
for pt = 0, 12 do
    t( "primitiveType=" .. pt, function()
        mesh.Begin( pt, 100, "Debug/DebugMaterial" )
        mesh.Quad( v1, v2, v3, v4 )
    end )
end

print( "--- что означает count (тип=4, 1 квад) ---" )
for _, c in ipairs( { 0, 1, 2, 3, 4, 6, 8 } ) do
    t( "count=" .. c, function()
        mesh.Begin( 4, c, "Debug/DebugMaterial" )
        mesh.Quad( v1, v2, v3, v4 )
    end )
end

print( "--- сколько квадов допустимо при count=N (тип=4) ---" )
for _, c in ipairs( { 1, 2, 3, 4, 6 } ) do
    t( "count=" .. c .. ", 4 квада", function()
        mesh.Begin( 4, c, "Debug/DebugMaterial" )
        for _ = 1, 4 do mesh.Quad( v1, v2, v3, v4 ) end
    end )
end

print( "--- верхняя граница count ---" )
for _, c in ipairs( { 1000, 10000, 60000, 100000 } ) do
    t( "count=" .. c, function()
        mesh.Begin( 4, c, "Debug/DebugMaterial" )
        mesh.Quad( v1, v2, v3, v4 )
    end )
end

print( "--- нужен ли материал ---" )
t( "Begin(pt,count) без материала", function()
    mesh.Begin( 4, 100 )
    mesh.Quad( v1, v2, v3, v4 )
end )
t( "Begin(pt,count,Material())", function()
    mesh.Begin( 4, 100, Material( "Debug/DebugMaterial" ) )
    mesh.Quad( v1, v2, v3, v4 )
end )

print( "--- цвет: SetColorMaterial + Begin без материала ---" )
t( "SetColorMaterial + Begin(pt,count)", function()
    render.SetColorMaterial( Color( 255, 0, 0, 255 ) )
    mesh.Begin( 4, 100 )
    mesh.Quad( v1, v2, v3, v4 )
end )

print( "--- VertexCount / сколько вершин занял квад ---" )
t( "VertexCount после 2 квадов", function()
    mesh.Begin( 4, 100, "Debug/DebugMaterial" )
    mesh.Quad( v1, v2, v3, v4 )
    mesh.Quad( v1, v2, v3, v4 )
    print( "    vertexCount=" .. tostring( mesh.VertexCount() ) )
end )

print( "=== d1meshprobe4 done ===" )
