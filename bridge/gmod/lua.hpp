// lua.hpp — заголовки Lua 5.1 для d1bridge_dll
// Линкуется против GMod: garrysmod/bin/lua_shared.dll (x86)
// Тип lua_State намеренно непрозрачный — нам достаточно указателя.

#ifndef LUA_HPP_MINIMAL
#define LUA_HPP_MINIMAL

extern "C" {

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>

typedef struct lua_State lua_State;
typedef double lua_Number;
typedef ptrdiff_t lua_Integer;
typedef int (*lua_CFunction)(lua_State* L);

// Основное API (только то, что реально экспортирует lua_shared.dll)
int         lua_gettop(lua_State* L);
void        lua_settop(lua_State* L, int idx);
void        lua_pushvalue(lua_State* L, int idx);
void        lua_remove(lua_State* L, int idx);
void        lua_insert(lua_State* L, int idx);
void        lua_replace(lua_State* L, int idx);
int         lua_checkstack(lua_State* L, int sz);
void        lua_xmove(lua_State* from, lua_State* to, int n);
int         lua_isnumber(lua_State* L, int idx);
int         lua_isstring(lua_State* L, int idx);
int         lua_iscfunction(lua_State* L, int idx);
int         lua_isuserdata(lua_State* L, int idx);
int         lua_type(lua_State* L, int idx);
const char* lua_typename(lua_State* L, int t);
int         lua_equal(lua_State* L, int idx1, int idx2);
int         lua_rawequal(lua_State* L, int idx1, int idx2);
int         lua_lessthan(lua_State* L, int idx1, int idx2);
lua_Number  lua_tonumber(lua_State* L, int idx);
lua_Integer lua_tointeger(lua_State* L, int idx);
int         lua_toboolean(lua_State* L, int idx);
const char* lua_tolstring(lua_State* L, int idx, size_t* len);
size_t      lua_objlen(lua_State* L, int idx);
lua_CFunction lua_tocfunction(lua_State* L, int idx);
void*       lua_touserdata(lua_State* L, int idx);
lua_State*  lua_tothread(lua_State* L, int idx);
const void* lua_topointer(lua_State* L, int idx);
void        lua_pushnil(lua_State* L);
void        lua_pushnumber(lua_State* L, lua_Number n);
void        lua_pushinteger(lua_State* L, lua_Integer n);
void        lua_pushlstring(lua_State* L, const char* s, size_t l);
void        lua_pushstring(lua_State* L, const char* s);
const char* lua_pushvfstring(lua_State* L, const char* fmt, va_list argp);
const char* lua_pushfstring(lua_State* L, const char* fmt, ...);
void        lua_pushcclosure(lua_State* L, lua_CFunction fn, int n);
void        lua_pushboolean(lua_State* L, int b);
void        lua_pushlightuserdata(lua_State* L, void* p);
int         lua_pushthread(lua_State* L);
void        lua_gettable(lua_State* L, int idx);
void        lua_getfield(lua_State* L, int idx, const char* k);
void        lua_rawget(lua_State* L, int idx);
void        lua_rawgeti(lua_State* L, int idx, int n);
void        lua_createtable(lua_State* L, int narr, int nrec);
void*       lua_newuserdata(lua_State* L, size_t sz);
int         lua_getmetatable(lua_State* L, int objindex);
void        lua_getfenv(lua_State* L, int idx);
void        lua_settable(lua_State* L, int idx);
void        lua_setfield(lua_State* L, int idx, const char* k);
void        lua_rawset(lua_State* L, int idx);
void        lua_rawseti(lua_State* L, int idx, int n);
int         lua_setmetatable(lua_State* L, int objindex);
void        lua_setfenv(lua_State* L, int idx);
void        lua_call(lua_State* L, int nargs, int nresults);
int         lua_pcall(lua_State* L, int nargs, int nresults, int errfunc);
int         lua_cpcall(lua_State* L, lua_CFunction func, void* ud);
int         lua_load(lua_State* L, const char* (*reader)(lua_State*, void*, size_t*), void* dt, const char* chunkname);
int         lua_dump(lua_State* L, int (*writer)(lua_State*, const void*, size_t, void*), void* data);
int         lua_yield(lua_State* L, int nresults);
int         lua_resume(lua_State* L, int narg);
int         lua_status(lua_State* L);
int         lua_gc(lua_State* L, int what, int data);
int         lua_error(lua_State* L);
int         lua_next(lua_State* L, int idx);
void        lua_concat(lua_State* L, int n);
lua_Number  lua_tonumberx(lua_State* L, int idx, int* isnum);
lua_Integer lua_tointegerx(lua_State* L, int idx, int* isnum);
int         lua_isinteger(lua_State* L, int idx);
unsigned int lua_version(lua_State* L);
int         lua_absindex(lua_State* L, int idx);
int         lua_sethook(lua_State* L, void (*func)(lua_State*, void*), int mask, int count);
void*       lua_gethook(lua_State* L);
int         lua_gethookmask(lua_State* L);
int         lua_gethookcount(lua_State* L);
void        lua_getfenv_(lua_State* L, int idx);

// Вспомогательные функции
int         luaL_error(lua_State* L, const char* fmt, ...);
int         luaL_argerror(lua_State* L, int numarg, const char* extramsg);
const char* luaL_checklstring(lua_State* L, int numArg, size_t* l);
const char* luaL_optlstring(lua_State* L, int numArg, const char* def, size_t* l);
lua_Number  luaL_checknumber(lua_State* L, int numArg);
lua_Number  luaL_optnumber(lua_State* L, int nArg, lua_Number def);
lua_Integer luaL_checkinteger(lua_State* L, int numArg);
lua_Integer luaL_optinteger(lua_State* L, int nArg, lua_Integer def);
void        luaL_checkstack(lua_State* L, int sz, const char* msg);
void        luaL_checktype(lua_State* L, int narg, int t);
void        luaL_checkany(lua_State* L, int narg);
int         luaL_newmetatable(lua_State* L, const char* tname);
void*       luaL_checkudata(lua_State* L, int ud, const char* tname);
void        luaL_where(lua_State* L, int lvl);
int         luaL_ref(lua_State* L, int t);
void        luaL_unref(lua_State* L, int t, int ref);
const char* luaL_gsub(lua_State* L, const char* s, const char* p, const char* r);
const char* luaL_findtable(lua_State* L, int idx, const char* fname, int szhint);
int         luaL_traceback(lua_State* L, lua_State* L1, const char* msg, int level);

} // extern "C"

// Константы
#define LUA_MULTRET          (-1)
#define LUA_REGISTRYINDEX    (-10000)
#define LUA_ENVIRONINDEX     (-10001)
#define LUA_GLOBALSINDEX     (-10002)
#define LUA_TNONE            (-1)
#define LUA_TNIL             0
#define LUA_TBOOLEAN         1
#define LUA_TLIGHTUSERDATA   2
#define LUA_TNUMBER          3
#define LUA_TSTRING          4
#define LUA_TTABLE           5
#define LUA_TFUNCTION        6
#define LUA_TUSERDATA        7
#define LUA_TTHREAD          8
#define LUA_ERRRUN           2
#define LUA_ERRSYNTAX        3
#define LUA_ERRMEM           4
#define LUA_ERRERR           5
#define LUA_YIELD            1
#define LUA_VERSION_NUM      501

// Макросы
#define lua_pop(L,n)             lua_settop(L, -(n)-1)
#define lua_newtable(L)          lua_createtable(L, 0, 0)
#define lua_register(L,n,f)      (lua_pushcfunction(L, (f)), lua_setglobal(L, (n)))
#define lua_pushcfunction(L,f)   lua_pushcclosure(L, (f), 0)
#define lua_strlen(L,i)          lua_objlen(L, (i))
#define lua_isfunction(L,n)      (lua_type(L, (n)) == LUA_TFUNCTION)
#define lua_istable(L,n)         (lua_type(L, (n)) == LUA_TTABLE)
#define lua_islightuserdata(L,n) (lua_type(L, (n)) == LUA_TLIGHTUSERDATA)
#define lua_isnil(L,n)           (lua_type(L, (n)) == LUA_TNIL)
#define lua_isboolean(L,n)       (lua_type(L, (n)) == LUA_TBOOLEAN)
#define lua_isthread(L,n)        (lua_type(L, (n)) == LUA_TTHREAD)
#define lua_isnone(L,n)          (lua_type(L, (n)) == LUA_TNONE)
#define lua_isnoneornil(L,n)     (lua_type(L, (n)) <= 0)
#define lua_pushliteral(L,s)     lua_pushlstring(L, "" s, (sizeof(s)/sizeof(char))-1)
#define lua_setglobal(L,s)       lua_setfield(L, LUA_GLOBALSINDEX, (s))
#define lua_getglobal(L,s)       lua_getfield(L, LUA_GLOBALSINDEX, (s))
#define lua_tostring(L,i)        lua_tolstring(L, (i), NULL)

#endif // LUA_HPP_MINIMAL
