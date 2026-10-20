-- d1logtest.lua — проверка каналов записи лога (показывает ОШИБКИ)
-- Запуск: lua_openscript_cl "autorun/client/d1logtest.lua"

print( "=== d1logtest ===" )

-- Канал 1: file.Append в DATA
local ok1, err1 = pcall( function()
    file.Append( "d1bridge/d1logtest.txt", "DATA", "test append\n" )
end )
print( string.format( "file.Append(DATA): ok=%s err=%s", tostring( ok1 ), tostring( err1 ) ) )

-- Канал 2: file.Write в DATA (с корневым именем)
local ok2, err2 = pcall( function()
    file.Write( "d1logtest2.txt", "DATA", "test write\n" )
end )
print( string.format( "file.Write(DATA): ok=%s err=%s", tostring( ok2 ), tostring( err2 ) ) )

-- Канал 3: io.open по абсолютному пути
local abs = "D:/SteamLibrary/steamapps/common/GarrysMod/garrysmod/data/d1logtest3.txt"
local ok3, err3 = pcall( function()
    local f = assert( io.open( abs, "a" ) )
    f:write( "test io.open\n" )
    f:close()
end )
print( string.format( "io.open(abs): ok=%s err=%s", tostring( ok3 ), tostring( err3 ) ) )

-- Канал 4: io.open по относительному пути
local ok4, err4 = pcall( function()
    local f = assert( io.open( "d1logtest4.txt", "a" ) )
    f:write( "test io.open rel\n" )
    f:close()
end )
print( string.format( "io.open(rel): ok=%s err=%s", tostring( ok4 ), tostring( err4 ) ) )

-- Канал 5: file.Write в "GAME" (корень garrysmod)
local ok5, err5 = pcall( function()
    file.Write( "d1logtest5.txt", "GAME", "test write game\n" )
end )
print( string.format( "file.Write(GAME): ok=%s err=%s", tostring( ok5 ), tostring( err5 ) ) )

-- Где мы находимся?
print( "CurDir() = " .. tostring( CurDir and CurDir() ) )
print( "file.Exists('d1logtest.txt','DATA') = " ..
    tostring( file.Exists( "d1logtest.txt", "DATA" ) ) )

print( "=== d1logtest done ===" )
