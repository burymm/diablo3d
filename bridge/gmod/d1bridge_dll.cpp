// d1bridge_dll.cpp — Lua-модуль для GMod: чтение shared memory D1BridgeState
// Р-25: GMod читает shared memory напрямую, без файлов и Python-моста
//
// Сборка: cl /LD /EHsc d1bridge_dll.cpp /I<path_to_lua_headers> /link /OUT:d1bridge.dll
// Или через MSBuild (d1bridge_dll.vcxproj)

#include <windows.h>
#include <lua.hpp>
#include <string.h>
#include <stdio.h>

// Имя shared memory
#define D1BRIDGE_SHM_NAME "D1BridgeState"
#define D1BRIDGE_MAGIC   0x31423144  // 'D1B1'
#define D1BRIDGE_VERSION 1

// Размеры (должны совпадать с d1bridge.cpp)
#define FINE_MAP_SIZE   (112 * 112)
#define TBW_SIZE        2049
#define PLAYER_MAP_SIZE (112 * 112)

// Структуры (должны совпадать с d1bridge.cpp)
#pragma pack(push, 1)
struct D1BridgeHeader {
    uint32_t magic;
    uint32_t version;
    uint32_t seq;
    uint32_t player_size;   // sizeof(D1BridgePlayer) — читатели определяют раскладку
    uint64_t timestamp_ms;
};

struct D1BridgePlayer {
    int16_t  Row;
    int16_t  Col;
    int16_t  dir;
    int16_t  dungeon;
    int16_t  CurAction;   // PCA_0_STAND = 0 — герой стоит и готов к шагу
    int16_t  padding;
    int32_t  CurLife;
    int32_t  MaxCurLife;
    int32_t  CurMana;
    int32_t  MaxCurMana;
    int16_t  CharLevel;
    uint16_t ClassID;
    int64_t  Xp;
    int32_t  TotalGold;
    char     name[32];
};

struct D1BridgeCommand {
    uint32_t seq;
    uint32_t action;
    int32_t  param1;
    int32_t  param2;
    int32_t  param3;
    int32_t  param4;
    uint32_t timestamp_ms;
};

struct D1BridgeState {
    D1BridgeHeader header;
    D1BridgePlayer player;
    D1BridgeCommand command;
    int32_t  FineMap[FINE_MAP_SIZE];
    uint8_t  TileBlockWalking[TBW_SIZE];
    uint8_t  PlayerMap[PLAYER_MAP_SIZE];
};
#pragma pack(pop)

// Дескрипторы shared memory
static HANDLE g_hMapFile = NULL;
static D1BridgeState* g_pState = NULL;
static uint32_t g_cmdSeq = 0;

// --- Динамические смещения -------------------------------------------------
//
// Размер структуры игрока публикуется в header.player_size. Это позволяет
// читателю работать с любой версией TH4: если сборки расходятся (например,
// DLL старая, а TH4 новый), достаточно пересчитать смещения, а не падать.
//
// Раскладка D1BridgePlayer:
//   v2 (76 байт): Row i16, Col i16, dir i16, dungeon i16, CurAction i16,
//                  pad i16, CurLife i32, MaxCurLife i32, CurMana i32,
//                  MaxCurMana i32, CharLevel i16, ClassID u16, Xp i64,
//                  TotalGold i32, name[32]
//   v1 (72 байта): то же, но без CurAction/pad.
#define PLAYER_V1_SIZE 72
#define PLAYER_V2_SIZE 76

#define OFF_HEADER      0
#define OFF_PLAYER      24
#define COMMAND_SIZE    28
#define FINE_MAP_BYTES  (FINE_MAP_SIZE * 4)

static uint32_t g_playerSize = 0;   // из заголовка
static uint32_t g_offCommand = 0;
static uint32_t g_offFineMap = 0;
static uint32_t g_offTbw = 0;
static uint32_t g_offPlayerMap = 0;

// Смещения полей внутри структуры игрока
static int g_fCurAction = -1;   // -1 = поля нет (старая версия)

static void D1BridgeRecalcLayout()
{
    g_playerSize = g_pState ? g_pState->header.player_size : 0;

    // Неизвестная/нулевая версия — считаем по-старому
    if (g_playerSize != PLAYER_V2_SIZE) {
        g_playerSize = PLAYER_V1_SIZE;
        g_fCurAction = -1;
    } else {
        g_fCurAction = 8;   // int16 CurAction после dungeon
    }

    g_offCommand   = OFF_PLAYER + g_playerSize;
    g_offFineMap   = g_offCommand + COMMAND_SIZE;
    g_offTbw       = g_offFineMap + FINE_MAP_BYTES;
    g_offPlayerMap = g_offTbw + TBW_SIZE;
}

// Чтение полей игрока по смещениям (структуры не используем — раскладка может отличаться)
static int16_t D1GetI16(uint32_t off)
{
    int16_t v = 0;
    memcpy(&v, (const uint8_t*)g_pState + off, sizeof(v));
    return v;
}
static int32_t D1GetI32(uint32_t off)
{
    int32_t v = 0;
    memcpy(&v, (const uint8_t*)g_pState + off, sizeof(v));
    return v;
}
static int64_t D1GetI64(uint32_t off)
{
    int64_t v = 0;
    memcpy(&v, (const uint8_t*)g_pState + off, sizeof(v));
    return v;
}

// Абсолютные смещения полей игрока (для текущей раскладки)
static uint32_t D1PlayerField(int idx)
{
    // idx: 0=Row 1=Col 2=dir 3=dungeon 4=CurLife 5=MaxCurLife 6=CurMana
    //      7=MaxCurMana 8=CharLevel 9=ClassID 10=Xp 11=TotalGold 12=name
    if (g_playerSize == PLAYER_V2_SIZE) {
        static const uint32_t off[] = {
            0, 2, 4, 6, 12, 16, 20, 24, 28, 30, 32, 40, 44
        };
        return OFF_PLAYER + off[idx];
    }
    static const uint32_t off[] = {
        0, 2, 4, 6, 8, 12, 16, 20, 24, 26, 28, 36, 40
    };
    return OFF_PLAYER + off[idx];
}

// Открыть shared memory
static bool D1BridgeOpen()
{
    if (g_pState) return true;

    g_hMapFile = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, D1BRIDGE_SHM_NAME);
    if (!g_hMapFile) return false;

    // Мапим максимальный размер — с запасом на любую версию
    g_pState = (D1BridgeState*)MapViewOfFile(g_hMapFile, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(D1BridgeState));
    if (!g_pState) {
        CloseHandle(g_hMapFile);
        g_hMapFile = NULL;
        return false;
    }

    // Определяем раскладку по заголовку
    D1BridgeRecalcLayout();

    return true;
}

// Закрыть shared memory
static void D1BridgeClose()
{
    if (g_pState) {
        UnmapViewOfFile(g_pState);
        g_pState = NULL;
    }
    if (g_hMapFile) {
        CloseHandle(g_hMapFile);
        g_hMapFile = NULL;
    }
}

// Lua: d1bridge_open() -> bool
static int l_d1bridge_open(lua_State* L)
{
    bool ok = D1BridgeOpen();
    lua_pushboolean(L, ok);
    return 1;
}

// Lua: d1bridge_close()
static int l_d1bridge_close(lua_State* L)
{
    D1BridgeClose();
    return 0;
}

// Lua: d1bridge_read() -> table or nil
static int l_d1bridge_read(lua_State* L)
{
    if (!g_pState) {
        lua_pushnil(L);
        return 1;
    }

    // Проверяем magic
    if (g_pState->header.magic != D1BRIDGE_MAGIC) {
        lua_pushnil(L);
        return 1;
    }

    // Раскладка могла измениться (новая сборка TH4) — пересчитываем
    if (g_pState->header.player_size != g_playerSize) {
        D1BridgeRecalcLayout();
    }

    // Создаём таблицу с данными героя
    lua_newtable(L);

    lua_pushstring(L, "Row");
    lua_pushinteger(L, D1GetI16(D1PlayerField(0)));
    lua_settable(L, -3);

    lua_pushstring(L, "Col");
    lua_pushinteger(L, D1GetI16(D1PlayerField(1)));
    lua_settable(L, -3);

    lua_pushstring(L, "dir");
    lua_pushinteger(L, D1GetI16(D1PlayerField(2)));
    lua_settable(L, -3);

    lua_pushstring(L, "dungeon");
    lua_pushinteger(L, D1GetI16(D1PlayerField(3)));
    lua_settable(L, -3);

    if (g_fCurAction >= 0) {
        lua_pushstring(L, "CurAction");
        lua_pushinteger(L, D1GetI16(OFF_PLAYER + g_fCurAction));
        lua_settable(L, -3);
    }

    lua_pushstring(L, "CurLife");
    lua_pushinteger(L, D1GetI32(D1PlayerField(4)));
    lua_settable(L, -3);

    lua_pushstring(L, "MaxCurLife");
    lua_pushinteger(L, D1GetI32(D1PlayerField(5)));
    lua_settable(L, -3);

    lua_pushstring(L, "CurMana");
    lua_pushinteger(L, D1GetI32(D1PlayerField(6)));
    lua_settable(L, -3);

    lua_pushstring(L, "MaxCurMana");
    lua_pushinteger(L, D1GetI32(D1PlayerField(7)));
    lua_settable(L, -3);

    lua_pushstring(L, "CharLevel");
    lua_pushinteger(L, D1GetI16(D1PlayerField(8)));
    lua_settable(L, -3);

    lua_pushstring(L, "ClassID");
    lua_pushinteger(L, D1GetI16(D1PlayerField(9)));
    lua_settable(L, -3);

    lua_pushstring(L, "Xp");
    lua_pushinteger(L, (lua_Integer)D1GetI64(D1PlayerField(10)));
    lua_settable(L, -3);

    lua_pushstring(L, "TotalGold");
    lua_pushinteger(L, D1GetI32(D1PlayerField(11)));
    lua_settable(L, -3);

    lua_pushstring(L, "name");
    lua_pushstring(L, (const char*)((const uint8_t*)g_pState + D1PlayerField(12)));
    lua_settable(L, -3);

    lua_pushstring(L, "timestamp_ms");
    lua_pushinteger(L, (lua_Integer)g_pState->header.timestamp_ms);
    lua_settable(L, -3);

    return 1;
}

// Lua: d1bridge_read_map() -> { fine = {...}, tbw = {...}, players = {...} }
// Карта уровня из shared memory: FineMap (тайлы), TileBlockWalking (стены),
// PlayerMap (кто стоит в клетке). Нужна для 3D-сцены в GMod.
static int l_d1bridge_read_map(lua_State* L)
{
    if (!g_pState) {
        lua_pushnil(L);
        return 1;
    }
    if (g_pState->header.magic != D1BRIDGE_MAGIC) {
        lua_pushnil(L);
        return 1;
    }
    if (g_pState->header.player_size != g_playerSize) {
        D1BridgeRecalcLayout();
    }

    const uint8_t* base = (const uint8_t*)g_pState;

    lua_newtable(L);

    // fine = { [1..112*112] = tileIndex }
    lua_newtable(L);
    for (int i = 0; i < FINE_MAP_SIZE; i++) {
        int32_t v = 0;
        memcpy(&v, base + g_offFineMap + i * 4, sizeof(v));
        lua_pushinteger(L, v);
        lua_rawseti(L, -2, i + 1);
    }
    lua_setfield(L, -2, "fine");

    // tbw = { [1..2049] = 0|1..10 }  (0 = можно ходить)
    lua_newtable(L);
    for (int i = 0; i < TBW_SIZE; i++) {
        lua_pushinteger(L, (lua_Integer)base[g_offTbw + i]);
        lua_rawseti(L, -2, i + 1);
    }
    lua_setfield(L, -2, "tbw");

    // players = { [1..112*112] = id }
    lua_newtable(L);
    for (int i = 0; i < PLAYER_MAP_SIZE; i++) {
        lua_pushinteger(L, (lua_Integer)(int8_t)base[g_offPlayerMap + i]);
        lua_rawseti(L, -2, i + 1);
    }
    lua_setfield(L, -2, "players");

    return 1;
}

// Lua: d1bridge_send_command(action, param1, param2) -> bool
static int l_d1bridge_send_command(lua_State* L)
{
    if (!g_pState) {
        lua_pushboolean(L, false);
        return 1;
    }
    if (g_pState->header.magic != D1BRIDGE_MAGIC) {
        lua_pushboolean(L, false);
        return 1;
    }
    if (g_pState->header.player_size != g_playerSize) {
        D1BridgeRecalcLayout();
    }

    uint32_t action = (uint32_t)lua_tointeger(L, 1);
    int32_t param1 = (int32_t)lua_tointeger(L, 2);
    int32_t param2 = (int32_t)lua_tointeger(L, 3);

    // Пишем структуру команды по вычисленному смещению
    uint8_t* cmd = (uint8_t*)g_pState + g_offCommand;
    uint32_t seq = ++g_cmdSeq;
    uint32_t ts = (uint32_t)GetTickCount();
    uint32_t zeros[2] = { 0, 0 };
    memcpy(cmd + 0,  &seq,    4);
    memcpy(cmd + 4,  &action, 4);
    memcpy(cmd + 8,  &param1, 4);
    memcpy(cmd + 12, &param2, 4);
    memcpy(cmd + 16, zeros,   4);
    memcpy(cmd + 20, zeros,   4);
    memcpy(cmd + 24, &ts,     4);

    lua_pushboolean(L, true);
    return 1;
}

// Lua: d1bridge_read_map_area(row, col, radius) -> { w, h, tiles, walls, players }
//
// Локальная область карты вокруг героя. Гораздо быстрее, чем читать всю
// карту 112x112 через Lua (12544 элементов).
//
// tiles[i]  = ID тайла в клетке (0 = пусто)
// walls[i]  = 1 если клетка непроходима (стена)
// players[i]= ID игрока/монстра в клетке (0 = пусто)
static int l_d1bridge_read_map_area(lua_State* L)
{
    if (!g_pState) {
        lua_pushnil(L);
        return 1;
    }
    if (g_pState->header.magic != D1BRIDGE_MAGIC) {
        lua_pushnil(L);
        return 1;
    }
    if (g_pState->header.player_size != g_playerSize) {
        D1BridgeRecalcLayout();
    }

    int centerRow = (int)lua_tointeger(L, 1);
    int centerCol = (int)lua_tointeger(L, 2);
    int radius = (int)lua_tointeger(L, 3);
    if (radius < 1) radius = 1;
    if (radius > 56) radius = 56;

    const uint8_t* base = (const uint8_t*)g_pState;
    const int32_t* fine = (const int32_t*)(base + g_offFineMap);
    const uint8_t* tbw = base + g_offTbw;
    const int8_t* pmap = (const int8_t*)(base + g_offPlayerMap);

    int w = radius * 2 + 1;
    int h = radius * 2 + 1;
    int count = w * h;

    lua_newtable(L);

    // tiles
    lua_newtable(L);
    for (int i = 0; i < count; i++) {
        int dr = i / w - radius;
        int dc = i % w - radius;
        int rr = centerRow + dr;
        int cc = centerCol + dc;
        int32_t tile = 0;
        if (rr >= 0 && rr < 112 && cc >= 0 && cc < 112) {
            tile = fine[rr * 112 + cc];
        }
        lua_pushinteger(L, tile);
        lua_rawseti(L, -2, i + 1);
    }
    lua_setfield(L, -2, "tiles");

    // walls — стена это TileBlockWalking[ID тайла] != 0
    lua_newtable(L);
    for (int i = 0; i < count; i++) {
        int dr = i / w - radius;
        int dc = i % w - radius;
        int rr = centerRow + dr;
        int cc = centerCol + dc;
        int wall = 0;
        if (rr >= 0 && rr < 112 && cc >= 0 && cc < 112) {
            int32_t tile = fine[rr * 112 + cc];
            if (tile != 0 && tile < TBW_SIZE && tbw[tile] != 0) {
                wall = 1;
            }
        }
        lua_pushinteger(L, wall);
        lua_rawseti(L, -2, i + 1);
    }
    lua_setfield(L, -2, "walls");

    // players
    lua_newtable(L);
    for (int i = 0; i < count; i++) {
        int dr = i / w - radius;
        int dc = i % w - radius;
        int rr = centerRow + dr;
        int cc = centerCol + dc;
        int pid = 0;
        if (rr >= 0 && rr < 112 && cc >= 0 && cc < 112) {
            pid = pmap[rr * 112 + cc];
        }
        lua_pushinteger(L, pid);
        lua_rawseti(L, -2, i + 1);
    }
    lua_setfield(L, -2, "players");

    // Метаданные
    lua_pushstring(L, "w");
    lua_pushinteger(L, w);
    lua_settable(L, -3);

    lua_pushstring(L, "h");
    lua_pushinteger(L, h);
    lua_settable(L, -3);

    lua_pushstring(L, "radius");
    lua_pushinteger(L, radius);
    lua_settable(L, -3);

    lua_pushstring(L, "origin_row");
    lua_pushinteger(L, centerRow - radius);
    lua_settable(L, -3);

    lua_pushstring(L, "origin_col");
    lua_pushinteger(L, centerCol - radius);
    lua_settable(L, -3);

    return 1;
}

// Lua: d1bridge_is_open() -> bool
static int l_d1bridge_is_open(lua_State* L)
{
    lua_pushboolean(L, g_pState != NULL);
    return 1;
}

// Lua: d1bridge_abi_version() -> int
// Версия ABI модуля. Аддон проверяет её, чтобы не использовать устаревшую
// сборку DLL (которая не знает про player_size и ломает раскладку).
#define D1BRIDGE_ABI_VERSION 2

static int l_d1bridge_abi_version(lua_State* L)
{
    lua_pushinteger(L, D1BRIDGE_ABI_VERSION);
    return 1;
}

// Трассировка: какой экспорт вызывает GMod
// (включается установкой D1BRIDGE_TRACE в 1)
#define D1BRIDGE_TRACE 0

#if D1BRIDGE_TRACE
static void D1Trace(const char* what)
{
    char path[MAX_PATH];
    GetModuleFileNameA(NULL, path, MAX_PATH);
    char* slash = strrchr(path, '\\');
    if (slash) *(slash + 1) = 0;
    strcat(path, "d1bridge_trace.txt");

    FILE* f = fopen(path, "a");
    if (!f) return;
    fprintf(f, "%s\n", what);
    fclose(f);
}
#else
#define D1Trace(x) ((void)0)
#endif

// Точка входа для Lua
//
// GMod (lua_shared) ищет бинарные модули по шаблону:
//   garrysmod/lua/bin/gm<cl|sv>_<имя>_<суффикс>.dll
//   (cl — клиент, sv — сервер; суффикс: win64 / win32 / linux64 / osx64)
//
// и вызывает экспорт "gmod13_open" (сигнатура как у luaopen_*).
// Дополнительно экспортируем "gmod13_close" — GMod вызывает его при выгрузке.
//
// Путь в GMod: file.Exists("lua/bin/gmcl_d1bridge_win64.dll", "MOD")
extern "C" __declspec(dllexport) int gmod13_open(lua_State* L)
{
    int argc = lua_gettop(L);
    lua_newtable(L);

    lua_pushstring(L, "open");
    lua_pushcfunction(L, l_d1bridge_open);
    lua_settable(L, -3);

    lua_pushstring(L, "close");
    lua_pushcfunction(L, l_d1bridge_close);
    lua_settable(L, -3);

    lua_pushstring(L, "read");
    lua_pushcfunction(L, l_d1bridge_read);
    lua_settable(L, -3);

    lua_pushstring(L, "send_command");
    lua_pushcfunction(L, l_d1bridge_send_command);
    lua_settable(L, -3);

    lua_pushstring(L, "is_open");
    lua_pushcfunction(L, l_d1bridge_is_open);
    lua_settable(L, -3);

    lua_pushstring(L, "abi_version");
    lua_pushcfunction(L, l_d1bridge_abi_version);
    lua_settable(L, -3);

    lua_pushstring(L, "read_map");
    lua_pushcfunction(L, l_d1bridge_read_map);
    lua_settable(L, -3);

    lua_pushstring(L, "read_map_area");
    lua_pushcfunction(L, l_d1bridge_read_map_area);
    lua_settable(L, -3);

    // Саморегистрация в package.loaded["<имя>"].
    //
    // GMod вызывает gmod13_open(L, <путь к DLL>) — единственный аргумент это
    // полный путь, а не имя модуля. Имя выводим из пути:
    //   ...\gmcl_d1bridge_win64.dll  ->  "d1bridge"
    //   ...\gmsv_mymod_win32.dll     ->  "mymod"
    // GMod затем возвращает пользователю package.loaded[<имя>].
    {
        static char derived[128];
        derived[0] = 0;

        const char* path = (argc >= 1) ? lua_tolstring(L, 1, NULL) : NULL;
        if (!path) {
            char self[MAX_PATH];
            GetModuleFileNameA(NULL, self, MAX_PATH);
            path = self;
        }

        // отбрасываем директорию
        const char* base = path;
        for (const char* p = path; *p; p++) {
            if (*p == '\\' || *p == '/') base = p + 1;
        }

        strncpy(derived, base, sizeof(derived) - 1);
        derived[sizeof(derived) - 1] = 0;

        // отбрасываем расширение .dll
        char* dot = strrchr(derived, '.');
        if (dot) *dot = 0;

        // отбрасываем суффикс архитектуры (_win64 / _win32 / _linux64 ...)
        char* und = strrchr(derived, '_');
        if (und && strlen(und) <= 8) *und = 0;

        // отбрасываем префикс gmcl_ / gmsv_
        if (strncmp(derived, "gmcl_", 5) == 0) memmove(derived, derived + 5, strlen(derived + 5) + 1);
        else if (strncmp(derived, "gmsv_", 5) == 0) memmove(derived, derived + 5, strlen(derived + 5) + 1);

        char tb[256];
        sprintf(tb, "gmod13_open: registering as '%s'", derived);
        D1Trace(tb);

        // package.loaded[modName] = <таблица модуля>
        lua_getglobal(L, "package");
        if (lua_type(L, -1) == LUA_TTABLE) {
            lua_getfield(L, -1, "loaded");
            if (lua_type(L, -1) == LUA_TTABLE) {
                lua_pushvalue(L, -3);      // наша таблица модуля
                lua_setfield(L, -2, derived);
            }
            lua_pop(L, 1);
        }
        lua_pop(L, 1);

        // GMod ведёт свой реестр _MODULES[имя] = true
        lua_getglobal(L, "_MODULES");
        if (lua_type(L, -1) == LUA_TTABLE) {
            lua_pushboolean(L, 1);
            lua_setfield(L, -2, derived);
        }
        lua_pop(L, 1);

        // И глобальная переменная с именем модуля
        lua_pushvalue(L, -2);   // таблица модуля
        lua_setglobal(L, derived);
    }

    return 1;
}

// Выгрузка модуля: закрываем shared memory
extern "C" __declspec(dllexport) int gmod13_close(lua_State* L)
{
    D1Trace("gmod13_close called");
    D1BridgeClose();
    return 0;
}

// Алиас для стандартного Lua-загрузчика (require в других окружениях)
extern "C" __declspec(dllexport) int luaopen_d1bridge(lua_State* L)
{
    D1Trace("luaopen_d1bridge called");
    return gmod13_open(L);
}

// DllMain — ловим момент загрузки DLL
BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID lpReserved)
{
    if (reason == DLL_PROCESS_ATTACH) {
        D1Trace("DllMain: PROCESS_ATTACH");
    } else if (reason == DLL_PROCESS_DETACH) {
        D1Trace("DllMain: PROCESS_DETACH");
    }
    return TRUE;
}
