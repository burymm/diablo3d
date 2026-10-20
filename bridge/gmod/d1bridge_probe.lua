-- d1bridge_probe.lua — диагностика загрузки бинарного модуля GMod
-- Запуск: lua_openscript_cl "autorun/client/d1bridge_probe.lua"
print("=== d1bridge probe ===")

local function dump(t, prefix)
    if type(t) ~= "table" then return end
    for k, v in pairs(t) do
        print(prefix .. tostring(k) .. " = " .. type(v))
    end
end

for _, n in ipairs({ "d1bdiag3", "d1bridge" }) do
    local ok, mod = pcall(require, n)
    print(string.format("require('%s') ok=%s value=%s (type=%s)",
        n, tostring(ok), tostring(mod), type(mod)))
    if ok and type(mod) == "table" then
        dump(mod, "   ")
        if mod.open then
            print("   mod.open() = " .. tostring(mod.open()))
            local p = mod.read()
            if p then
                print(string.format("   read: %s Lvl=%d Row=%d Col=%d HP=%d Mana=%d/%d",
                    tostring(p.name), p.CharLevel or -1, p.Row or -1, p.Col or -1,
                    p.CurLife or -1, p.CurMana or -1, p.MaxCurMana or -1))
            else
                print("   read() = nil")
            end
        end
    end
    if package and package.loaded then
        print("   package.loaded['" .. n .. "'] type = " .. type(package.loaded[n]))
        if type(package.loaded[n]) == "table" then
            dump(package.loaded[n], "      ")
            if package.loaded[n].open then
                print("      .open() = " .. tostring(package.loaded[n].open()))
            end
        end
    end
    -- глобальная переменная с именем модуля
    local g = rawget(_G, n)
    print("   _G['" .. n .. "'] type = " .. type(g))
    if type(g) == "table" then dump(g, "      ") end
end

print("=== probe done ===")
