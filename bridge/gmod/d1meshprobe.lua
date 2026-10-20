-- d1meshprobe.lua — выясняем точный API мешей и рендера в этом GMod.
-- Запуск: lua_openscript_cl "autorun/client/d1meshprobe.lua"

print( "=== d1meshprobe ===" )

print( "GAMEMODE_NAME = " .. tostring( GAMEMODE_NAME ) )
print( "type(mesh)    = " .. type( mesh ) )

if type( mesh ) == "table" then
    local keys = {}
    for k, v in pairs( mesh ) do
        keys[#keys+1] = k .. "(" .. type( v ) .. ")"
    end
    table.sort( keys )
    print( "mesh API: " .. table.concat( keys, ", " ) )
end

-- Что есть в render для отрисовки
local rkeys = {}
for k, v in pairs( render ) do
    local lk = string.lower( k )
    if lk:find( "mesh" ) or lk:find( "draw" ) or lk:find( "beam" )
       or lk:find( "sprite" ) or lk:find( "model" ) then
        rkeys[#rkeys+1] = k .. "(" .. type( v ) .. ")"
    end
end
table.sort( rkeys )
print( "render API: " .. table.concat( rkeys, ", " ) )

-- Пробуем создать меш разными способами
local function try( name, fn )
    local ok, err = pcall( fn )
    print( string.format( "  %-28s ok=%-5s %s", name, tostring( ok ),
        ok and "" or tostring( err ) ) )
    return ok
end

local madeBegin = try( "mesh.Begin/End", function()
    mesh.Begin( "Debug/DebugMaterial" )
    mesh.Vertex( Vector( 0, 0, 0 ) )
    mesh.Vertex( Vector( 200, 0, 0 ) )
    mesh.Vertex( Vector( 0, 200, 0 ) )
    mesh.End()
end )

local madeStart = try( "mesh.Start/End", function()
    mesh.Start( "D1ProbeMesh" )
    mesh.Vertex( Vector( 0, 0, 0 ) )
    mesh.Vertex( Vector( -200, 0, 0 ) )
    mesh.Vertex( Vector( 0, -200, 0 ) )
    mesh.End()
end )

try( "mesh.SetColor", function()
    mesh.SetColor( 255, 128, 0, 255 )
end )

try( "mesh.Clear", function()
    mesh.Clear()
end )

-- Отрисовка готового меша
try( "render.DrawMesh(name,mat,pos,ang)", function()
    render.DrawMesh( "D1ProbeMesh", "Debug/DebugMaterial", Vector( 0, 0, 0 ), Angle( 0, 0, 0 ) )
end )

try( "render.DrawMesh(name,mat,x,y,z,ang)", function()
    render.DrawMesh( "D1ProbeMesh", "Debug/DebugMaterial", 0, 0, 0, Angle( 0, 0, 0 ) )
end )

try( "render.DrawMesh(name,mat,pos,ang,mat4)", function()
    render.DrawMesh( "D1ProbeMesh", "Debug/DebugMaterial", Vector( 0, 0, 0 ), Angle( 0, 0, 0 ), Matrix() )
end )

-- Что умеет render в плане цвета
try( "render.SetColorMaterial", function()
    render.SetColorMaterial( Color( 255, 120, 0, 255 ) )
end )

-- Есть ли утилиты для геометрии
for _, n in ipairs( { "Vector", "Angle", "Color", "Matrix", "LocalPlayer",
                      "render", "surface", "cam", "util", "system" } ) do
    print( string.format( "  global %-12s = %s", n, type( _G[n] ) ) )
end

print( "madeBegin=" .. tostring( madeBegin ) ..
       " madeStart=" .. tostring( madeStart ) )
print( "=== d1meshprobe done ===" )
