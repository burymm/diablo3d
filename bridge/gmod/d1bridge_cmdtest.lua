-- d1bridge_cmdtest.lua — проверка нативной отправки команд в TH4
-- Запуск: lua_openscript_cl "autorun/client/d1bridge_cmdtest.lua"
--
-- Отправляет команду через DLL и печатает, что реально оказалось
-- в разделяемой памяти (её читает TH4 и применяет в Player.destAction).

local mod = (package and package.loaded) and package.loaded["d1bridge"]
if type(mod) ~= "table" then
    pcall(require, "d1bridge")
    mod = (package and package.loaded) and package.loaded["d1bridge"]
end

if type(mod) ~= "table" then
    print("[cmdtest] FAIL: модуль d1bridge не найден")
    return
end

print("[cmdtest] модуль найден, open = " .. tostring(mod.open()))
if not mod.open() then
    print("[cmdtest] FAIL: shared memory недоступна (th43d.exe запущен?)")
    return
end

-- Направления -> PLAYER_COMMAND (см. enums.h TH4)
local DIRS = {
    { name = "up",         code = 5 },
    { name = "up-right",   code = 1 },
    { name = "up-left",    code = 2 },
    { name = "right",      code = 6 },
    { name = "down-right", code = 3 },
    { name = "down",       code = 7 },
    { name = "down-left",  code = 4 },
    { name = "left",       code = 8 },
}

print("[cmdtest] --- отправка команд ---")
for _, d in ipairs(DIRS) do
    local ok = mod.send_command(d.code, 0, 0)
    print(string.format("[cmdtest] %-11s -> action=%d  send=%s",
        d.name, d.code, tostring(ok)))
    -- небольшая пауза, чтобы TH4 успел обработать
    timer.Simple(0.35, function() end)
end

print("[cmdtest] --- проверка в TH4 ---")
print("[cmdtest] Смотри на героя в окне TH4: он должен двигаться.")
print("[cmdtest] Лог TH4: e:\\games\\TheHell3D\\d1bridge.log")
