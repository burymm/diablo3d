-- d1polyprobe.lua — как именно работает surface.DrawPoly в этой сборке GMod.
-- Запуск: lua_openscript_cl "autorun/client/d1polyprobe.lua"

-- Гасим изометрию, чтобы её чёрный фон не затерёл тестовые фигуры.
if D1Iso and D1Iso.Disable then
    D1Iso.Disable()
else
    RunConsoleCommand( "d1iso_bg 0" )
end

local function poly( verts, r, g, b )
    surface.SetDrawColor( r, g, b, 255 )
    surface.DrawPoly( verts )
end

hook.Add( "DrawOverlay", "d1polyprobe", function()
    local W, H = ScrW(), ScrH()

    -- Яркий фон всего экрана: если его видно — DrawOverlay работает
    surface.SetDrawColor( 90, 0, 90, 255 )
    surface.DrawRect( 0, 0, W, H )

    local u = math.min( W, H ) / 8

    -- 1. КРАСНЫЙ: вложенный формат {x,y}, обход против часовой
    poly( {
        { u, u }, { u - u/2, u + u/2 }, { u, u * 2 }, { u + u/2, u + u/2 }
    }, 255, 0, 0 )

    -- 2. ЗЕЛЁНЫЙ: вложенный формат {x,y}, обход по часовой
    poly( {
        { u * 3, u }, { u * 3 + u/2, u + u/2 }, { u * 3, u * 2 }, { u * 3 - u/2, u + u/2 }
    }, 0, 255, 0 )

    -- 3. СИНИЙ: плоский массив {x1,y1,x2,y2,...}
    poly( {
        u * 5, u, u * 5 + u/2, u + u/2, u * 5, u * 2, u * 5 - u/2, u + u/2
    }, 0, 80, 255 )

    -- 4. ЖЁЛТЫЙ: плоский массив, другой обход
    poly( {
        u * 7, u, u * 7 - u/2, u + u/2, u * 7, u * 2, u * 7 + u/2, u + u/2
    }, 255, 255, 0 )

    -- 5. ГОЛУБОЙ: вложенный формат с Vector(x,y)
    poly( {
        { Vector( u * 9, u ) }, { Vector( u * 9 + u/2, u + u/2 ) },
        { Vector( u * 9, u * 2 ) }, { Vector( u * 9 - u/2, u + u/2 ) }
    }, 0, 220, 255 )

    -- 6. ОРАНЖЕВЫЙ: триангуляр, плоский массив
    poly( { u * 11, u, u * 11 + u/2, u + u/2, u * 11, u * 2 }, 255, 140, 0 )

    -- Контроль: прямоугольники (заведомо работают)
    surface.SetDrawColor( 255, 255, 255, 255 )
    surface.DrawRect( 10, H - 40, 200, 30 )
    surface.SetDrawColor( 0, 255, 0, 255 )
    surface.DrawRect( 220, H - 40, 200, 30 )

    -- Контроль: повёрнутый текстурированный прямоугольник
    surface.SetDrawColor( 255, 255, 255, 255 )
    surface.DrawTexturedRectRotated( W - 120, H - 120, 120, 60, 30 )
end )

print( "=== d1polyprobe ===" )
print( "Фиолетовый фон + ромбы слева направо: КРАСНЫЙ, ЗЕЛЁНЫЙ, СИНИЙ," )
print( "ЖЁЛТЫЙ, ГОЛУБОЙ, ОРАНЖЕВЫЙ." )
print( "Внизу: белый и зелёный прямоугольники + белый повёрнутый." )
print( "=== d1polyprobe done ===" )
