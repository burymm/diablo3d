--[[--------------------------------------------------------------------------
    d1bridge.lua  —  GMod-клиент для Diablo 1 Bridge

    Источник данных (в приоритете):
      1) Бинарный Lua-модуль d1bridge.dll — читает разделяемую память
         D1BridgeState напрямую. Нулевая задержка, никаких файлов.
         Модуль: garrysmod/lua/modules/d1bridge.dll
      2) Файл garrysmod/data/d1bridge/snapshot.json — запасной путь
         (если DLL не загрузилась).

    Что делает:
      - читает состояние героя (HP/мана/уровень/золото/опыт/координаты);
      - рисует HUD-панель слева сверху;
      - показывает состояние связи: подключён ли мост, свежесть данных;
      - отправляет команды в TH4 (обратный канал).

    Команды в консоли GMod (~ или просто в чат):
      d1bridge_toggle   — показать/скрыть панель
      d1bridge_status   — вывести состояние связи в чат/консоль
--------------------------------------------------------------------------]]

local PATH  = "d1bridge/snapshot.json"
local POLL_INTERVAL = 0.1   -- 10 Гц — достаточно, чтение мгновенное
local STALE_AFTER    = 3.0   -- секунд; старше — считаем снимок протухшим

local visible = true
local snap    = nil        -- последний успешно прочитанный снимок
local snapAge = nil        -- возраст снимка в секундах (на момент чтения)
local lastErr = nil        -- последняя ошибка чтения/парсинга
local useDll  = false      -- читаем ли через бинарный модуль
local dll     = nil        -- ссылка на модуль

-- Пробуем загрузить бинарный модуль (прямой доступ к shared memory).
--
-- Механика GMod:
--   - модуль лежит в garrysmod/lua/bin/gm<cl|sv>_<имя>_<арх>.dll
--   - экспорт: gmod13_open(lua_State*, <путь к DLL>)
--   - модуль сам регистрирует себя в package.loaded[<имя>]
--   - require() возвращает nil (GMod кэширует модуль ДО вызова open),
--     поэтому берём таблицу из package.loaded после require.
--
-- Проверяем abi_version: модуль должен уметь читать player_size из
-- заголовка shared memory, иначе раскладка данных разъедется.
local MOD_NAME = "d1bridge"
local REQUIRED_ABI = 2

pcall(require, MOD_NAME)
dll = (package and package.loaded) and package.loaded[MOD_NAME] or nil

local function moduleAbi(m)
    if type(m) ~= "table" or not m.abi_version then return 0 end
    return m.abi_version()
end

if type(dll) == "table" and dll.open and moduleAbi(dll) >= REQUIRED_ABI then
    if dll.open() then
        useDll = true
        print("[d1bridge] бинарный модуль загружен: читаю D1BridgeState напрямую")
    else
        print("[d1bridge] модуль загружен, но shared memory недоступна " ..
              "(th43d.exe не запущен?) — читаю snapshot.json")
    end
elseif type(dll) == "table" and dll.open then
    print("[d1bridge] модуль устарел (abi=" .. moduleAbi(dll) ..
          "), нужен abi >= " .. REQUIRED_ABI .. " — пересобери DLL")
else
    print("[d1bridge] бинарный модуль недоступен (требуется d1bridge.dll " ..
          "в garrysmod/lua/bin/) — читаю snapshot.json")
end

local COLORS = {
    bg       = Color(18, 18, 22, 190),
    border   = Color(90, 90, 110, 200),
    hp       = Color(190, 40, 40, 235),
    hpLow    = Color(220, 70, 30, 235),
    mp       = Color(40, 90, 200, 235),
    xp       = Color(160, 120, 30, 235),
    text     = Color(230, 230, 235, 255),
    dim      = Color(150, 150, 160, 255),
    ok       = Color(70, 200, 110, 255),
    stale    = Color(230, 180, 60, 255),
    bad      = Color(230, 80, 80, 255),
}

-- Шрифты
surface.CreateFont("D1B_Header", {
    font = "Tahoma", size = 16, weight = "BOLD", antialias = true,
})
surface.CreateFont("D1B_Text", {
    font = "Tahoma", size = 14, antialias = true,
})
surface.CreateFont("D1B_Small", {
    font = "Tahoma", size = 12, antialias = true,
})

-- Чтение состояния героя из бинарного модуля (shared memory)
local function readFromDll()
    local p = dll.read()
    if not p then return nil end

    -- Модуль отдаёт поля напрямую; оборачиваем в тот же формат, что и JSON
    return {
        ts = SysTime(),
        ok = true,
        pid = 0,
        player = {
            Row = p.Row,
            Col = p.Col,
            dir = p.dir,
            dungeon = p.dungeon,
            CurLife = p.CurLife,
            MaxCurLife = p.MaxCurLife,
            CurMana = p.CurMana,
            MaxCurMana = p.MaxCurMana,
            CharLevel = p.CharLevel,
            ClassID = p.ClassID,
            Xp = p.Xp,
            TotalGold = p.TotalGold,
            name = p.name,
        },
        ack = "OK (shm)",
    }
end

local function readSnapshot()
    -- Путь 1: бинарный модуль (shared memory напрямую)
    if useDll and dll then
        local data = readFromDll()
        if data then
            snap = data
            lastErr = nil
            snapAge = 0
            return
        end
        -- shared memory недоступна — пробуем открыть заново
        if not dll.is_open() then
            dll.open()
        end
        snap = nil
        lastErr = "shared memory недоступна (th43d.exe не запущен?)"
        return
    end

    -- Путь 2: запасной — snapshot.json
    local raw = file.Read(PATH, "DATA")
    if not raw or raw == "" then
        snap = nil
        lastErr = "файл не найден"
        return
    end

    local parsed = util.JSONToTable(raw)
    if not parsed then
        snap = nil
        lastErr = "битый JSON (файл читается в момент записи?)"
        return
    end

    snap = parsed
    lastErr = nil

    -- возраст снимка
    if parsed.ts then
        local age = SysTime() - tonumber(parsed.ts)
        -- ts — unix-время Python; SysTime в GMod — системное, тоже unix.
        -- Если получилось отрицательное — часы/формат не совпали, игнорируем возраст.
        snapAge = (age >= 0) and age or nil
    end
end

-- Разбор fixed-point значений HP/маны (в TH4 они ×64)
local function fixed64(v)
    if type(v) ~= "number" then return nil, nil end
    return v / 64.0, v
end

-- Доля заполнения (0..1) с защитой от nil/0
local function frac(cur, max)
    if type(cur) ~= "number" or type(max) ~= "number" or max <= 0 then
        return 0
    end
    return cur / max
end

local function statusColor()
    if not snap then return COLORS.bad end
    if snap.ok == false then return COLORS.bad end
    if snapAge and snapAge > STALE_AFTER then return COLORS.stale end
    return COLORS.ok
end

local function statusText()
    if not snap then
        return "НЕТ ДАННЫХ (" .. tostring(lastErr or "нет файла") .. ")"
    end
    if snap.ok == false then
        return "reader: Player не найден (ok=false)"
    end
    if snapAge and snapAge > STALE_AFTER then
        return string.format("УСТАРЕЛО (%.1f c) — TH4 выключена или reader остановлен", snapAge)
    end
    return string.format("OK  pid=%s  возраст %.2f c", tostring(snap.pid or "?"),
           snapAge and snapAge or 0.0)
end

local function drawBar(x, y, w, h, frac, col, label, text)
    draw.RoundedBox(4, x, y, w, h, Color(0, 0, 0, 130))
    frac = math.Clamp(frac or 0, 0, 1)
    if frac > 0 then
        draw.RoundedBox(4, x, y, w * frac, h, col)
    end
    draw.SimpleText(label, "D1B_Text", x + 4, y + h * 0.5, COLORS.text, TEXT_ALIGN_LEFT,
            TEXT_ALIGN_CENTER)
    if text then
        draw.SimpleText(text, "D1B_Small", x + w - 4, y + h * 0.5, COLORS.text,
                TEXT_ALIGN_RIGHT, TEXT_ALIGN_CENTER)
    end
end

local DIR_NAMES = {
    [0] = "вверх", [1] = "вверх-вправо", [2] = "вправо", [3] = "вниз-вправо",
    [4] = "вниз", [5] = "вниз-влево", [6] = "влево", [7] = "вверх-влево",
}

local function drawHUD()
    if not visible then return end

    local x, y = 16, 90
    local w = 300
    local pad = 10
    local lineH = 16

    -- Считаем высоту по содержимому
    local p = snap and snap.player or nil
    local hasPlayer = (p ~= nil)

    local bodyH = 0
    if hasPlayer then
        bodyH = bodyH + 18 + 18        -- HP + MP
              + 6
              + lineH * 3              -- уровень/золото/опыт
              + 6
              + lineH * 3              -- dungeon, координаты, направление
    end
    local h = 30 + bodyH + (hasPlayer and 0 or 18)
    if not snap then h = 30 + 18 end

    -- Фон
    draw.RoundedBox(6, x, y, w, h, COLORS.bg)
    surface.SetDrawColor(COLORS.border)
    surface.DrawOutlinedRect(x, y, w, h)

    -- Заголовок + статус
    draw.SimpleText("Diablo Bridge", "D1B_Header", x + pad, y + pad, COLORS.text,
            TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP)
    draw.SimpleText(statusText(), "D1B_Small", x + w - pad, y + pad + 3,
            statusColor(), TEXT_ALIGN_RIGHT, TEXT_ALIGN_TOP)

    local cy = y + 30

    if not snap then
        draw.SimpleText("Запусти TH4 и: python d1reader.py watch",
                "D1B_Text", x + pad, cy, COLORS.dim, TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP)
        return
    end

    if not hasPlayer then
        draw.SimpleText("В снимке нет раздела player (ок = " .. tostring(snap.ok) .. ")",
                "D1B_Text", x + pad, cy, COLORS.dim, TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP)
        return
    end

    -- HP / Мана (fixed-point /64)
    local hp, hpRaw = fixed64(p.CurLife)
    local maxHp, maxHpRaw = fixed64(p.MaxCurLife)
    local mp, mpRaw = fixed64(p.CurMana)
    local maxMp, maxMpRaw = fixed64(p.MaxCurMana)

    local hpFrac = frac(hpRaw, maxHpRaw)
    local hpCol = (hpFrac <= 0.25) and COLORS.hpLow or COLORS.hp

    drawBar(x + pad, cy, w - pad * 2, 16, hpFrac, hpCol, "HP",
            string.format("%d / %d", math.floor(hp or 0), math.floor(maxHp or 0)))
    cy = cy + 18

    drawBar(x + pad, cy, w - pad * 2, 16, frac(mpRaw, maxMpRaw),
            COLORS.mp, "Мана",
            string.format("%d / %d", math.floor(mp or 0), math.floor(maxMp or 0)))
    cy = cy + 18 + 6

    -- Уровень / золото / опыт
    draw.SimpleText(string.format("Уровень: %s", tostring(p.CharLevel or "?")),
            "D1B_Text", x + pad, cy, COLORS.text, TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP)
    draw.SimpleText(string.format("Золото: %s", tostring(p.TotalGold or "?")),
            "D1B_Text", x + w - pad, cy, COLORS.text, TEXT_ALIGN_RIGHT, TEXT_ALIGN_TOP)
    cy = cy + lineH

    draw.SimpleText(string.format("Опыт: %s", tostring(p.Xp or "?")),
            "D1B_Text", x + pad, cy, COLORS.text, TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP)
    draw.SimpleText(string.format("Класс: %s", tostring(p.ClassID or "?")),
            "D1B_Text", x + w - pad, cy, COLORS.text, TEXT_ALIGN_RIGHT, TEXT_ALIGN_TOP)
    cy = cy + lineH

    -- Имя
    draw.SimpleText(string.format("Герой: %s", tostring(p.name or "?")),
            "D1B_Text", x + pad, cy, COLORS.text, TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP)
    cy = cy + lineH + 6

    -- Dungeon / координаты / направление
    local dnum = tonumber(p.dungeon)
    local dungeonName = dnum and (("Уровень %d"):format(dnum)) or "?"
    draw.SimpleText(string.format("Подземелье: %s", dungeonName),
            "D1B_Small", x + pad, cy, COLORS.dim, TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP)
    draw.SimpleText(string.format("Ярус: %s", tostring(p.dungeon or "?")),
            "D1B_Small", x + w - pad, cy, COLORS.dim, TEXT_ALIGN_RIGHT, TEXT_ALIGN_TOP)
    cy = cy + lineH

    draw.SimpleText(string.format("Координаты: Row=%s  Col=%s",
            tostring(p.Row or "?"), tostring(p.Col or "?")),
            "D1B_Small", x + pad, cy, COLORS.dim, TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP)
    draw.SimpleText(string.format("base=%s", p.base and ("0x%X"):format(p.base) or "?"),
            "D1B_Small", x + w - pad, cy, COLORS.dim, TEXT_ALIGN_RIGHT, TEXT_ALIGN_TOP)
    cy = cy + lineH

    local d = tonumber(p.dir)
    draw.SimpleText(string.format("Направление: %s (%s)",
            DIR_NAMES[d] or "?", tostring(p.dir or "?")),
            "D1B_Small", x + pad, cy, COLORS.dim, TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP)
    cy = cy + lineH

    -- обратный канал: последний ответ reader'а
    local ack = snap.ack
    if ack then
        lastAck = ack
        local okAck = string.find(ack, "OK") ~= nil or string.find(ack, "pong") ~= nil
        local age = ""
        if snap.ack_ts and snap.ts then
            age = string.format("  [%.1f c назад]", math.max(0, snap.ts - snap.ack_ts))
        end
        draw.SimpleText(string.format("cmd: %s%s", tostring(ack), age),
                "D1B_Small", x + pad, cy,
                okAck and COLORS.ok or COLORS.stale,
                TEXT_ALIGN_LEFT, TEXT_ALIGN_TOP)
    end
end

-- Опрашиваем файл
timer.Create("d1bridge_poll", POLL_INTERVAL, 0, readSnapshot)

-- Рисуем каждый кадр
hook.Add("HUDPaint", "d1bridge_hud", drawHUD)

-- Команды
concommand.Add("d1bridge_toggle", function()
    visible = not visible
    chat.AddText(Color(70, 200, 110), "[d1bridge] ", Color(230, 230, 235),
            visible and "панель показана" or "панель скрыта")
end)

concommand.Add("d1bridge_status", function()
    chat.AddText(Color(70, 200, 110), "[d1bridge] источник: ", Color(230, 230, 235),
            useDll and "shared memory (D1BridgeState) — напрямую" or PATH)
    chat.AddText(Color(70, 200, 110), "[d1bridge] статус: ", statusColor(), statusText())

    if snap and snap.player then
        local p = snap.player
        chat.AddText(Color(70, 200, 110), "[d1bridge] герой: ", Color(230, 230, 235),
                string.format("%s, ур.%s, HP=%s, золото=%s, Row/Col=%s/%s",
                        tostring(p.name), tostring(p.CharLevel),
                        tostring(p.CurLife), tostring(p.TotalGold),
                        tostring(p.Row), tostring(p.Col)))
    end

    -- обратный канал: последний ack от reader'а
    if snap and snap.ack then
        lastAck = snap.ack
        lastAckAt = CurTime()
        local ok = string.find(snap.ack, "OK") ~= nil
        chat.AddText(Color(70, 200, 110), "[d1bridge] ack: ",
                ok and Color(120, 230, 140) or Color(230, 180, 60), snap.ack)
    else
        chat.AddText(Color(70, 200, 110), "[d1bridge] ack: ", Color(150, 150, 160),
                "нет — отправь d1_ping или d1_click")
    end
end)

-- ==========================================================================
-- Обратный канал (этап 1): команды GMod -> TH4 кликами (Р-8 "клик-фолбэк")
--
-- GMod пишет bridge_cmd.json, reader (d1reader.py watch) читает его и
-- синтетически кликает в окно игры. Смещения в памяти TH4 не нужны —
-- игра сама решает, что делать.
-- ==========================================================================
local CMD_PATH = "d1bridge/bridge_cmd.json"
local cmdSeq = 0
local lastAck = nil
local lastAckAt = 0

-- Режим ввода в TH4:
--   false (по умолчанию) — «курсор + PostMessage»: окно TH4 можно оставить
--       на втором мониторе или просто перекрытым GMod, фокус не забирается.
--       ВАЖНО: окно TH4 должно быть РАЗВЁРНУТЫМ — свёрнутое окно игра
--       не обрабатывает вообще (проверено 16.10.2026).
--   true                   — настоящий курсор с поднятием окна (окно
--       должно быть видно и забирает фокус) — запасной вариант.
local D1_REAL_CLICK = false

-- «Держу клавишу»: пока зажат один из WASD/QEZC, шлём шаги в TH4.
-- Направление -> (клавиша, сторона света в терминах TH4).
--
-- ВАЖНО: по умолчанию ВЫКЛЮЧЕНО. Основное управление — в d1control.lua
-- (FPS-режим: WASD относительно камеры). Старый режим оставлен как
-- запасной (на случай, если d1control.lua не загрузился) и включается
-- вручную командой d1_hold 1.
local D1_HOLD = {
    enabled = false,
    len = 3,                  -- на сколько клеток просить за один клик
    -- У каждого направления несколько источников нажатия:
    --   KEY_*  — физический код клавиши (ломается на не-US раскладке:
    --             с русской раскладкой физическая W даёт VKEY 0xE6 «Ц»);
    --   IN_*   — «движение» движка GMod (то, что игрок настроил в binds),
    --             раскладконезависимо.
    dirs = {
        { name = "up",         keys = { KEY_W, IN_FORWARD } },
        { name = "down",       keys = { KEY_S, IN_BACK } },
        { name = "left",       keys = { KEY_A, IN_MOVELEFT } },
        { name = "right",      keys = { KEY_D, IN_MOVERIGHT } },
        { name = "up-left",    keys = { KEY_Q } },
        { name = "up-right",   keys = { KEY_E } },
        { name = "down-left",  keys = { KEY_Z } },
        { name = "down-right", keys = { KEY_C } },
    },
}
local d1Held = { dir = nil }
-- Идентификатор сессии GMod: меняется при перезапуске игры/консоли.
-- Reader по нему сбрасывает дедупликацию, иначе после рестарта GMod
-- счётчик SysTime начинается с нуля и команды отфильтровываются навсегда.
local CMD_SID = tostring(os.time()) .. "-" .. tostring(math.random(1000, 9999))

-- Маппинг направлений в PLAYER_COMMAND (см. enums.h TH4)
local DIR_TO_CMD = {
    ["up"]         = 5,  -- PCMD_5_WALKU
    ["up-right"]   = 1,  -- PCMD_1_WALKUR
    ["up-left"]    = 2,  -- PCMD_2_WALKUL
    ["right"]      = 6,  -- PCMD_6_WALKR
    ["down-right"] = 3,  -- PCMD_3_WALKDR
    ["down"]       = 7,  -- PCMD_7_WALKD
    ["down-left"]  = 4,  -- PCMD_4_WALKDL
    ["left"]       = 8,  -- PCMD_8_WALKL
}

-- Отправка команды через shared memory (нативный destAction в TH4)
-- Возвращает true, если команда ушла в TH4 напрямую.
local function sendCmdShm(tbl)
    if not (useDll and dll) then return false end
    if not dll.is_open() then dll.open() end

    local action = nil
    if tbl.action == "hold" and tbl.dir then
        action = DIR_TO_CMD[tbl.dir]
    elseif tbl.action == "step" and tbl.dir then
        action = DIR_TO_CMD[tbl.dir]
    elseif tbl.action == "stand" then
        action = 0
    else
        return false  -- остальные команды пока через старый канал
    end

    if not action then return false end
    return dll.send_command(action, 0, 0) and true or false
end

local function sendCmd(tbl)
    cmdSeq = cmdSeq + 1
    tbl.seq = cmdSeq
    -- ts — SysTime(), а не os.time(): нужна субсекундная точность, иначе две
    -- команды в пределах одной секунды считаются одной (reader дедуплицирует
    -- по ts, потому что seq сбрасывается при рестарте).
    tbl.ts = SysTime()
    tbl.sid = CMD_SID

    -- Путь 1: native shared memory -> Player.destAction (мгновенно, без кликов)
    local viaShm = sendCmdShm(tbl)

    -- Путь 2: запасной — файл bridge_cmd.json (клик-фолбэк)
    local ok = true
    if not viaShm then
        ok = file.Write(CMD_PATH, util.TableToJSON(tbl))
        if not ok then
            chat.AddText(Color(230, 80, 80), "[d1bridge] НЕ смог записать команду: ",
                    Color(230, 230, 235), CMD_PATH)
            return false
        end
    end

    local extra = ""
    if tbl.action == "click" then
        extra = string.format(" в точку (%.2f, %.2f)", tonumber(tbl.x) or 0.5,
                              tonumber(tbl.y) or 0.5)
    elseif tbl.action == "step" or tbl.action == "hold" then
        extra = string.format(" %s%s", tostring(tbl.dir or ""),
                              (tonumber(tbl.n) or 1) > 1 and (" x" .. tbl.n) or "")
    end
    if tbl.quiet then
        -- режим удержания: сообщение о каждом шаге засоряло бы чат
        d1Held.lastOk = ok
        d1Held.lastSeq = tbl.seq
        d1Held.viaShm = viaShm
        return true
    end
    chat.AddText(Color(70, 200, 110), "[d1bridge] команда отправлена: ",
            Color(230, 230, 235), tbl.action .. extra,
            Color(150, 150, 160),
            viaShm and " (нативно, destAction)" or string.format(" (seq=%d)", cmdSeq))
    if not viaShm and not D1_REAL_CLICK and tbl.action ~= "ping" then
        chat.AddText(Color(150, 150, 160), "[d1bridge] ",
                "окно TH4 не в фокусе, курсор не забирается (окно должно быть развёрнуто).")
    end
    return true
end

-- Клик в нормализованных координатах окна игры (0..1).
local function clickAt(nx, ny)
    return sendCmd({ action = "click", x = nx, y = ny, real = D1_REAL_CLICK })
end

concommand.Add("d1_click", function(_, _, args)
    local nx, ny = tonumber(args[1]), tonumber(args[2])
    if not nx or not ny then
        chat.AddText(Color(70, 200, 110), "[d1bridge] ", Color(230, 230, 235),
                "клик в центр окна игры (герой пойдёт к центру экрана)")
        return clickAt(0.5, 0.5)
    end
    return clickAt(nx, ny)
end, function(_, _, str)
    return "d1_click [x y] — отправить клик в окно TH4 (координаты 0..1, по умолчанию центр)"
end)

concommand.Add("d1_ping", function()
    sendCmd({ action = "ping" })
end, function()
    return "d1_ping — проверить, что reader видит команды"
end)

-- Движение в клетках. Геометрию экрана считает reader (у него есть позиция
-- героя и размер окна), поэтому отсюда уходят клетки, а не пиксели.
-- Направления: up up-right right down-right down down-left left up-left
-- (короткие синонимы: w a s d q e z c).
--
-- d1_hold — «держу клавишу»: пока WASD/QEZC зажат, GMod шлёт шаги пачкой.
-- Нужно потому, что TH4 сам скорость не даёт увеличить: единственный способ
-- идти дальше — повторно подтверждать направление.
-- Диагностика ввода: показывает, какие источники GMod сейчас видит нажатыми.
-- Нужна, если удержание не работает (обычная причина — не-US раскладка).
concommand.Add("d1_keys", function()
    chat.AddText(Color(70, 200, 110), "[d1bridge] нажатые клавиши сейчас:",
        Color(230, 230, 235), " (держи WASD и повтори)")
    local any = false
    for i = 1, #D1_HOLD.dirs do
        local d = D1_HOLD.dirs[i]
        local hits = {}
        for k = 1, #d.keys do
            if input.IsKeyDown(d.keys[k]) then
                hits[#hits + 1] = d.keys[k]
                any = true
            end
        end
        if #hits > 0 then
            chat.AddText(Color(70, 200, 110), "  " .. d.name .. ": ",
                Color(230, 230, 235), table.concat(hits, ", "))
        end
    end
    if not any then
        chat.AddText(Color(230, 180, 60), "  ничего не нажато (или раскладка не та: ",
            Color(230, 230, 235), "GMod жмёт клавиши по раскладке Windows)")
    end
end, function()
    return "d1_keys — показать, какие клавиши движения GMod видит нажатыми"
end)

concommand.Add("d1_hold", function(_, _, args)
    local a = tostring(args[1] or ""):lower()
    if a == "1" or a == "on" or a == "true" then
        D1_HOLD.enabled = true
    elseif a == "0" or a == "off" or a == "false" then
        D1_HOLD.enabled = false
    elseif a == "len" or a == "" then
        D1_HOLD.len = math.Clamp(tonumber(args[2]) or 4, 1, 12)
    end
    chat.AddText(Color(70, 200, 110), "[d1bridge] d1_hold: ",
        Color(230, 230, 235),
        D1_HOLD.enabled and "включено" or "выключено",
        Color(150, 150, 160),
        string.format(" | %d кл. за клик (кликает reader, когда герой стоит)",
                      D1_HOLD.len))
end, function()
    return "d1_hold [0|1|len N] — удержание WASD/QEZC (длина шага N)"
end)

concommand.Add("d1_step", function(_, _, args)
    local dir = args[1]
    if not dir then
        chat.AddText(Color(230, 180, 60), "[d1bridge] ",
            Color(230, 230, 235),
            "укажи направление: d1_step right | d1_step w 3 (на 3 клетки)")
        return
    end
    local n = tonumber(args[2])
    return sendCmd({ action = "step", dir = dir, n = n or 1, real = D1_REAL_CLICK })
end, function(_, _, str)
    return "d1_step <направление> [клеток] — сдвинуть героя (по умолчанию 1)"
end)

concommand.Add("d1_goto", function(_, _, args)
    local row, col = tonumber(args[1]), tonumber(args[2])
    if not row or not col then
        chat.AddText(Color(230, 180, 60), "[d1bridge] ",
            Color(230, 230, 235), "укажи клетку: d1_goto 50 87")
        return
    end
    return sendCmd({ action = "goto", row = row, col = col, real = D1_REAL_CLICK })
end, function()
    return "d1_goto <row> <col> — идти в клетку"
end)

-- --------------------------------------------------------------------------
-- «Держу клавишу»: опрос в Think.
--
-- Логика: TH4 не даёт управлять скоростью, поэтому удержание клавиши
-- реализуется повторным подтверждением направления (клик на 1..8 клеток
-- вперёд каждые D1_HOLD.len секунд). Зажатые клавиши опрашиваются
-- каждый кадр, команда уходит не чаще интервала.
--
-- Если зажато несколько клавиш, побеждает та, которую нажали последней.
-- --------------------------------------------------------------------------
local function d1ThinkHeld()
    -- Если работает d1control.lua (FPS-управление) — не дублируем:
    -- он сам шлёт команды относительно камеры.
    if D1Control then return end

    if not D1_HOLD.enabled then
        if d1Held.dir then
            d1Held.dir = nil
            sendCmd({ action = "hold", dir = nil, real = D1_REAL_CLICK, quiet = true })
            chat.AddText(Color(150, 150, 160), "[d1bridge] удержание выключено")
        end
        return
    end

    -- какое направление нажато прямо сейчас (последнее из помеченных)
    local nowDir = nil
    for i = 1, #D1_HOLD.dirs do
        local d = D1_HOLD.dirs[i]
        for k = 1, #d.keys do
            if input.IsKeyDown(d.keys[k]) then
                nowDir = d.name
                break
            end
        end
    end

    if nowDir == d1Held.dir then return end

    if nowDir then
        -- ОДНА команда на нажатие. Дальше reader сам кликает, когда герой
        -- останавливается: курсор дёргается редко, а ходьба непрерывная.
        sendCmd({ action = "hold", dir = nowDir, n = D1_HOLD.len,
                  real = D1_REAL_CLICK, quiet = true })
        chat.AddText(Color(70, 200, 110), "[d1bridge] идём: ",
            Color(230, 230, 235), nowDir,
            Color(150, 150, 160),
            string.format(" (%d кл. за клик; reader сам продолжит)", D1_HOLD.len))
    elseif d1Held.dir then
        sendCmd({ action = "hold", dir = nil, real = D1_REAL_CLICK, quiet = true })
    end

    d1Held.dir = nowDir
end

hook.Add("Think", "d1bridge_hold", d1ThinkHeld)

-- Переключатель способа ввода без правки файла:
--   d1_mode post   — PostMessage (окно TH4 можно свернуть, фокус не трогаем)
--   d1_mode cursor — настоящий курсор (окно TH4 поднимается, забирает фокус)
concommand.Add("d1_mode", function(_, _, args)
    local m = tostring(args[1] or ""):lower()
    if m == "cursor" or m == "real" then
        D1_REAL_CLICK = true
    elseif m == "post" or m == "" then
        D1_REAL_CLICK = false
    else
        chat.AddText(Color(230, 180, 60), "[d1bridge] режим: ",
            Color(230, 230, 235), "post (PostMessage) или cursor (настоящий курсор)")
        return
    end
    chat.AddText(Color(70, 200, 110), "[d1bridge] режим ввода: ",
        Color(230, 230, 235),
        D1_REAL_CLICK and "настоящий курсор (фокус забирается)"
                          or "PostMessage (фокус не трогаем, окно можно свернуть)")
end, function()
    return "d1_mode [post|cursor] — как отправлять ввод в TH4"
end)

-- Ответ reader'а лежит в snapshot.json -> player/ack; читаем в status.
concommand.Add("d1_ack", function()
    local a = snap and snap.ack
    if a then
        local ok = string.find(a, "OK") ~= nil or string.find(a, "pong") ~= nil
        chat.AddText(Color(70, 200, 110), "[d1bridge] ack от reader: ",
                ok and Color(120, 230, 140) or Color(230, 180, 60), a)
    else
        chat.AddText(Color(230, 180, 60), "[d1bridge] ack: нет. ",
                Color(230, 230, 235),
                "reader запущен без поддержки команд — перезапусти d1bridge_watch.bat")
    end
end)

-- ---------------------------------------------------------------- контроллер
-- Поднимаем d1control.lua (FPS-управление: WASD относительно камеры).
-- Без него движение работало бы в старом режиме — «W всегда на север».
if not D1Control then
    pcall( dofile, "autorun/client/d1control.lua" )
end

print("[d1bridge] загружен. Команды: d1bridge_toggle, d1bridge_status, d1_step, d1_goto, d1_hold, d1_mode, d1_click, d1_keys, d1_ping, d1_ack")
print(string.format("[d1bridge] удержание WASD/QEZC (запасной режим): %s (%d кл. за клик)",
        D1_HOLD.enabled and "включено" or "выключено", D1_HOLD.len))
if D1Control then
    print("[d1bridge] активен d1control: WASD относительно камеры, ПКМ — обзор")
end
