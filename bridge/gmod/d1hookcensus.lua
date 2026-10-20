-- d1hookcensus.lua — перепись хуков GMod: какие реально вызываются.
-- Запуск: lua_openscript_cl "autorun/client/d1hookcensus.lua"
-- Потом: d1census

print( "=== d1hookcensus ===" )

local names = {
    -- логика
    "Think", "Tick", "SetupDataTables", "SetupMove", "Move", "PlayerSpawn",
    "PlayerInitialSpawn", "OnGamemodeLoaded", "PostCleanupMap", "InitPostEntity",
    -- рендер
    "PreDraw", "PostDraw", "PreRender", "PostRender", "PreRenderHooks",
    "PostRenderHooks", "CalcView", "CalcPostView", "RenderScreenshots",
    "ViewVectors", "RenderScene", "DrawHUD", "DrawOverlay",
    -- интерфейс
    "HUDPaint", "HUDShouldDraw", "PlayerButtonPress", "PlayerMouseWheel",
    "PlayerNoClip", "ChatText",
}

local counts = {}
for _, n in ipairs( names ) do
    counts[n] = 0
    local key = "d1census_" .. n
    hook.Add( n, key, function()
        counts[n] = counts[n] + 1
    end )
end

concommand.Add( "d1census", function()
    print( "===== d1census =====" )
    for _, n in ipairs( names ) do
        if counts[n] > 0 then
            print( string.format( "  %-22s %d", n, counts[n] ) )
        end
    end
    print( "  --- не вызвались ---" )
    for _, n in ipairs( names ) do
        if counts[n] == 0 then
            print( string.format( "  %-22s 0", n ) )
        end
    end
    print( string.format( "SysTime=%.2f CurTime=%.2f RealTime=%.2f",
        SysTime(), CurTime(), RealTime() ) )
    local ply = Entity( 1 )
    if ply and ply:IsValid() then
        print( "player pos=" .. tostring( ply:GetPos() ) ..
               " angles=" .. tostring( ply:GetAngles() ) )
    else
        print( "player: НЕТ" )
    end
    print( "LocalPlayer=" .. tostring( LocalPlayer and LocalPlayer() ) )
    print( "====================" )
end )

print( "=== d1hookcensus готов, выполни d1census через пару секунд ===" )
