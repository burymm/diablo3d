#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
d1reader.py — минимальный reader памяти TH4 для проекта diablo-1-source.

Только ЧТЕНИЕ памяти. Ничего в игру не пишет.

Команды:
  info
      Показать процесс игры (th43d.exe), модуль, разрядность; записать snapshot.json со
      статической информацией (проверка, что контакт есть).

  bootstrap --name "ИмяГероя"
      ОДНОРАЗОВАЯ инициализация: ищет структуру игрока по имени, находит
      статический указатель Players в модуле, вычисляет offsets.json.
      Запускать, когда герой УЖЕ в игре (не в главном меню).

  watch
      Читает значения по offsets.json и постоянно пишет snapshot.json.
      Запускать в отдельном окне, пока играете.

  hexdump --addr 0x1234 --size 128
      Показать байты по адресу (для ручного анализа).

Примеры:
  python d1reader.py info
  python d1reader.py bootstrap --name "Kadgar"
  python d1reader.py watch
"""

import argparse
import ctypes
import json
import os
import struct
import sys
import time

from ctypes import wintypes

# ----------------------------------------------------------------------------
# Целевая сборка игры
# ----------------------------------------------------------------------------
# Работаем ТОЛЬКО с инструментированной сборкой в e:\games\TheHell3D\
# (оригинальная e:\games\The Hell IV\ — не трогать, там сейвы/язык пользователя).
# Сборка: bridge\reader\build_th43d.bat → e:\games\TheHell3D\TH4.exe → копия в th43d.exe
TH4_EXE = "th43d.exe"          # имя процесса, за которым идёт мост
TH4_GAME_DIR = r"e:\games\TheHell3D"   # папка копии игры
D1MAP_EXPORT = "d1map_export.txt"      # экспорт адресов карты (пишет th43d.exe в свою папку)

# ----------------------------------------------------------------------------
# WinAPI
# ----------------------------------------------------------------------------

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010

MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

MAX_PATH = 260


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * MAX_PATH),
    ]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", ctypes.c_void_p),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * MAX_PATH),
    ]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
k32.Process32First.restype = wintypes.BOOL
k32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
k32.Process32Next.restype = wintypes.BOOL
k32.Module32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
k32.Module32First.restype = wintypes.BOOL
k32.Module32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
k32.Module32Next.restype = wintypes.BOOL
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.OpenProcess.restype = wintypes.HANDLE
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_size_t,
]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.IsWow64Process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
k32.IsWow64Process.restype = wintypes.BOOL


# ----------------------------------------------------------------------------
# Процесс / модули / чтение
# ----------------------------------------------------------------------------

def find_pid(exe_name=TH4_EXE):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        return None
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Process32First(snap, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile.decode("mbcs", "replace")
            if name.lower() == exe_name.lower():
                return entry.th32ProcessID
            ok = k32.Process32Next(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return None


def list_modules(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    mods = []
    if snap == INVALID_HANDLE_VALUE:
        return mods
    try:
        entry = MODULEENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Module32First(snap, ctypes.byref(entry))
        while ok:
            mods.append({
                "name": entry.szModule.decode("mbcs", "replace"),
                "base": entry.modBaseAddr or 0,
                "size": entry.modBaseSize,
                "path": entry.szExePath.decode("mbcs", "replace"),
            })
            ok = k32.Module32Next(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return mods


def open_process(pid):
    rights = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
    h = k32.OpenProcess(rights, False, pid)
    if not h:
        # запас: иногда лимитированных прав хватает
        h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    return h


_TYPE_FMT = {
    "u8": "<B", "i8": "<b", "u16": "<H", "i16": "<h",
    "u32": "<I", "i32": "<i", "u64": "<Q", "i64": "<q", "f32": "<f",
}


def unpack_value(data, off, typ):
    """Распаковывает значение из уже прочитанного буфера."""
    fmt = _TYPE_FMT[typ]
    size = struct.calcsize(fmt)
    if data is None or off < 0 or off + size > len(data):
        return None
    return struct.unpack_from(fmt, data, off)[0]


def read_bytes(handle, addr, size):
    buf = (ctypes.c_char * size)()
    read = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(read))
    if not ok or read.value != size:
        return None
    return buf.raw


def read_value(handle, addr, typ):
    fmt = _TYPE_FMT[typ]
    size = struct.calcsize(fmt)
    data = read_bytes(handle, addr, size)
    if data is None:
        return None
    return struct.unpack(fmt, data)[0]


def iter_regions(handle):
    mbi = MEMORY_BASIC_INFORMATION()
    addr = 0
    max_addr = 0x7FFF0000
    while addr < max_addr:
        if k32.VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(mbi),
                              ctypes.sizeof(mbi)) == 0:
            addr += 0x1000
            continue
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize or 0
        yield base, size, mbi
        nxt = base + size
        addr = nxt if nxt > addr else addr + 0x1000


def is_readable(mbi):
    if mbi.State != MEM_COMMIT:
        return False
    p = mbi.Protect
    if p == 0 or (p & PAGE_NOACCESS) or (p & PAGE_GUARD):
        return False
    return True


def scan_all(handle, needle, chunk=8 * 1024 * 1024):
    """Ищет needle (bytes) во всех читаемых регионах. Возвращает список адресов."""
    hits = []
    for base, size, mbi in iter_regions(handle):
        if not is_readable(mbi):
            continue
        off = 0
        carry = b""
        carry_addr = 0
        while off < size:
            n = min(chunk, size - off)
            data = read_bytes(handle, base + off, n)
            if data is None:
                # регион может частично не читаться — пропускаем целиком
                break
            block = carry + data
            start = 0
            while True:
                idx = block.find(needle, start)
                if idx < 0:
                    break
                hits.append(carry_addr + idx)
                start = idx + 1
            keep = len(needle) - 1
            carry = block[-keep:] if keep > 0 else b""
            carry_addr = base + off + n - len(carry)
            off += n
    return hits


MEM_PRIVATE = 0x20000
PAGE_WRITABLE = {0x04, 0x08, 0x40, 0x80}  # RW, WC, EXEC_RW, EXEC_WC


def is_writable(mbi):
    return mbi.State == MEM_COMMIT and mbi.Protect in PAGE_WRITABLE


def scan_module_writable(handle, mod_base, mod_size, needle):
    """Поиск needle в записываемых регионах внутри модуля (где живут глобалы)."""
    lo, hi = mod_base, mod_base + mod_size
    hits = []
    for base, size, mbi in iter_regions(handle):
        if base < lo or base >= hi:
            continue
        if not is_writable(mbi):
            continue
        data = read_bytes(handle, base, size)
        if data is None:
            continue
        start = 0
        while True:
            idx = data.find(needle, start)
            if idx < 0:
                break
            hits.append(base + idx)
            start = idx + 1
    return hits


def find_players_ptr(handle, mod_base, mod_size, player_base):
    """Ищет статическую переменную Players (указатель) в данных модуля."""
    for index in range(0, 8):
        arr_base = player_base - index * PLAYER_SIZE
        if arr_base <= 0:
            break
        pat = struct.pack("<I", arr_base & 0xFFFFFFFF)
        hits = scan_module_writable(handle, mod_base, mod_size, pat)
        if hits:
            return hits[0], arr_base, index
    return None


def collect_module_pointers(handle, mod_base, mod_size):
    """Собирает все 4-байтовые значения из записываемых данных модуля: value -> адрес."""
    lo, hi = mod_base, mod_base + mod_size
    dwords = {}
    for base, size, mbi in iter_regions(handle):
        if base < lo or base >= hi or not is_writable(mbi):
            continue
        data = read_bytes(handle, base, size)
        if data is None:
            continue
        for i in range(0, len(data) - 3, 4):
            v = int.from_bytes(data[i:i + 4], "little")
            if 0x10000 <= v < 0x80000000:
                dwords.setdefault(v, base + i)
    return dwords


_PRINTABLE_RUN = None  # инициализируется в find_player_candidates


def _i16(data, off):
    return int.from_bytes(data[off:off + 2], "little", signed=True)


def _i32(data, off):
    return int.from_bytes(data[off:off + 4], "little", signed=True)


def load_empirical_layout(path=None):
    """Загружает рабочую раскладку Player из offsets.json (запущенная сборка).

    В ней смещения отличаются от клона (docs/13). Если файла нет или он битый —
    возвращает клон-оверсеты как фолбэк.
    """
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "offsets.json")
    layout = {"name_off": PLAYER_NAME_OFF, "flags_off": PLAYER_FLAGS_OFF,
              "off": {k: v["off"] for k, v in PLAYER_FIELDS.items()}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return layout
    if data.get("name_off") is not None:
        layout["name_off"] = data["name_off"]
    if data.get("flags_off") is not None:
        layout["flags_off"] = data["flags_off"]
    if data.get("player_base_now") is not None:
        layout["player_base_now"] = data["player_base_now"]
    if data.get("player_name") is not None:
        layout["player_name"] = data["player_name"]
    for k, v in (data.get("fields") or {}).items():
        if isinstance(v, dict) and "off" in v and k in layout["off"]:
            layout["off"][k] = v["off"]
    return layout


def load_d1map_export(path=None):
    """Читает адреса карты, экспортированные инструментированной сборкой th43d.exe.

    Файл d1map_export.txt пишется в папку игры (TH4_GAME_DIR) при старте exe.
    Адреса НЕСТАБИЛЬНЫ между запусками — читать файл после каждого старта.
    Возвращает dict вида {"FineMap": 0x..., "TileBlockWalking": 0x...} или {}.
    """
    if path is None:
        path = os.path.join(TH4_GAME_DIR, D1MAP_EXPORT)
    out = {}
    try:
        with open(path, "r", encoding="ascii") as f:
            for line in f:
                line = line.strip()
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                try:
                    out[key.strip()] = int(val.strip(), 0)
                except ValueError:
                    continue
    except Exception:
        pass
    return out


def find_player_candidates(handle, chunk=8 * 1024 * 1024, overlap=0x200, layout=None):
    """Ищет структуры игрока в куче без имени: вид поля имени + строгая валидация.

    layout — словарь смещений запущенной сборки (из offsets.json). Если None,
    берётся offsets.json рядом со скриптом; если его нет — клон-оверсеты.
    """
    global _PRINTABLE_RUN
    if _PRINTABLE_RUN is None:
        import re
        _PRINTABLE_RUN = re.compile(rb"[\x20-\x7e]{2,31}\x00")

    # Смещения: сперва эмпирические (offsets.json), иначе клон.
    if layout is None:
        layout = load_empirical_layout()
    name_off = layout["name_off"]
    flags_off = layout["flags_off"]
    off_row = layout["off"]["Row"]
    off_col = layout["off"]["Col"]
    off_dir = layout["off"]["dir"]
    off_lvl = layout["off"]["CharLevel"]
    off_life = layout["off"]["CurLife"]
    off_mlife = layout["off"]["MaxCurLife"]
    # максимальное смещение среди проверяемых + 4 байта
    need = max(name_off + 32, off_mlife + 4)

    out = []
    seen = set()
    for base, size, mbi in iter_regions(handle):
        if not is_readable(mbi) or mbi.Type != MEM_PRIVATE or size == 0:
            continue
        off = 0
        while off < size:
            n = min(chunk, size - off)
            data = read_bytes(handle, base + off, n)
            if data is None:
                break
            for m in _PRINTABLE_RUN.finditer(data):
                s = m.start()
                co = s - name_off
                if co < 0 or co + need > len(data):
                    continue
                addr = base + off + co
                row = _i16(data, co + off_row)
                col = _i16(data, co + off_col)
                if not (0 <= row <= 111 and 0 <= col <= 111):
                    continue
                if not (0 <= data[co + off_dir] <= 7):      # dir
                    continue
                lvl = _i16(data, co + off_lvl)               # CharLevel
                if not (1 <= lvl <= 99):
                    continue
                life = _i32(data, co + off_life)
                mlife = _i32(data, co + off_mlife)
                if not (0 < mlife <= 10_000_000 and 0 <= life <= mlife):
                    continue
                if addr in seen:
                    continue
                seen.add(addr)
                # Живая копия: текущая жизнь > 0 (у "мёртвого" дубля life == 0).
                out.append({
                    "score": 6 + (1 if mlife % 64 == 0 else 0) + (2 if life > 0 else 0),
                    "base": addr,
                    "name": m.group()[:-1].decode("cp1251", "replace"),
                    "Row": row, "Col": col, "CharLevel": lvl,
                    "CurLife": life, "MaxCurLife": mlife,
                })
            if n <= overlap:
                break
            off += n - overlap
    out.sort(key=lambda x: (-x["score"], -x["CharLevel"]))
    return out


# ----------------------------------------------------------------------------
# Карта полей игрока (из исходников TH4: struct P_v25, structs.h)
# ----------------------------------------------------------------------------

PLAYER_SIZE = 0x18000  # sizeof(Player) для SaveVersion 26 (structs.h)

# Смещения посчитаны из реальной struct Player (structs.h, v26).
# Внимание: enum'ы здесь с базовым типом char (1 байт), Row/Col — short,
# IsExists — бит №3 в 32-битном наборе флагов по 0xA4.
PLAYER_FIELDS = {
    "CurAction":    {"off": 0x00, "type": "i8"},
    "fullClassId":  {"off": 0x1A, "type": "i8"},
    "destAction":   {"off": 0x1B, "type": "i8"},
    "destParam1":   {"off": 0x1C, "type": "i32"},
    "destParam2":   {"off": 0x20, "type": "i32"},
    "dungeon":      {"off": 0x2C, "type": "i8"},
    "Row":          {"off": 0x2E, "type": "i16"},
    "Col":          {"off": 0x30, "type": "i16"},
    "NextRow":      {"off": 0x32, "type": "i16"},
    "NextCol":      {"off": 0x34, "type": "i16"},
    "TargetRow":    {"off": 0x36, "type": "i16"},
    "TargetCol":    {"off": 0x38, "type": "i16"},
    "xOfs":         {"off": 0x44, "type": "i32"},
    "yOfs":         {"off": 0x48, "type": "i32"},
    "xVel":         {"off": 0x4C, "type": "i32"},
    "yVel":         {"off": 0x50, "type": "i32"},
    "dir":          {"off": 0x54, "type": "i8"},
    "nextDir":      {"off": 0x55, "type": "i8"},
    "Appearance":   {"off": 0x58, "type": "i32"},
    "ClassID":      {"off": 0xC9, "type": "i8"},
    "CurStrength":  {"off": 0xCA, "type": "i16"},
    "CurMagic":     {"off": 0xCE, "type": "i16"},
    "CurDexterity": {"off": 0xD2, "type": "i16"},
    "CurVitality":  {"off": 0xD6, "type": "i16"},
    "BaseDamage":   {"off": 0xDC, "type": "i32"},
    "BaseLife":     {"off": 0xE4, "type": "i32"},
    "CurLife":      {"off": 0xEC, "type": "i32"},
    "MaxCurLife":   {"off": 0xF0, "type": "i32"},
    "BaseMana":     {"off": 0xF8, "type": "i32"},
    "CurMana":      {"off": 0x100, "type": "i32"},
    "MaxCurMana":   {"off": 0x104, "type": "i32"},
    "CharLevel":    {"off": 0x10C, "type": "i16"},
    "Xp":           {"off": 0x110, "type": "i64"},
    "TotalGold":    {"off": 0x120, "type": "i32"},
    "CursorRow":    {"off": 0x124, "type": "i16"},
    "CursorCol":    {"off": 0x126, "type": "i16"},
}

PLAYER_FLAGS_OFF = 0xA4     # 32-битный набор флагов (bitfields)
PLAYER_ISEXISTS_BIT = 3     # runEnabled, meleeAttackBit, rangeAttackBit, IsExists
PLAYER_NAME_OFF = 0xA9
PLAYER_NAME_LEN = 32


def validate_player(handle, base, name_bytes, layout=None):
    """Проверяет, что по адресу base похоже на структуру игрока. Возвращает (ok, score, info).

    Валидация идёт по раскладке запущенной сборки (offsets.json), т.к. смещения
    клона отличаются (docs/13) и давали бы ложные кандидаты.
    """
    if layout is None:
        layout = load_empirical_layout()
    noff = layout["name_off"]
    f = layout["off"]

    name_field = read_bytes(handle, base + noff, PLAYER_NAME_LEN)
    if name_field is None:
        return False, 0, None
    if not name_field.startswith(name_bytes):
        return False, 0, None

    score = 1
    info = {"base": base}

    def ok_range(key, lo, hi):
        nonlocal score
        v = read_value(handle, base + f[key], PLAYER_FIELDS[key]["type"])
        info[key] = v
        if v is None:
            return False
        if lo <= v <= hi:
            score += 1
            return True
        return False

    ok_range("Row", 0, 112)
    ok_range("Col", 0, 112)
    ok_range("dir", 0, 8)
    ok_range("CharLevel", 1, 99)

    life = read_value(handle, base + f["CurLife"], "i32")
    max_life = read_value(handle, base + f["MaxCurLife"], "i32")
    info["CurLife"] = life
    info["MaxCurLife"] = max_life
    if life is not None and max_life is not None and 0 <= life <= 10_000_000 and 0 < max_life <= 10_000_000:
        score += 2

    gold = read_value(handle, base + f["TotalGold"], "i32")
    info["TotalGold"] = gold
    if gold is not None and 0 <= gold <= 100_000_000:
        score += 1

    # Строгий порог: нужны имя + Row + Col + dir + CharLevel + (life,maxlife) + gold.
    # Мусорные кандидаты с одними нулями дают score<=5 и отбрасываются.
    ok = score >= 8
    return ok, score, info


def read_player(handle, base, fields=None, name_off=None, flags_off=None, name_len=None):
    fields = fields if fields is not None else PLAYER_FIELDS
    name_off = PLAYER_NAME_OFF if name_off is None else name_off
    flags_off = PLAYER_FLAGS_OFF if flags_off is None else flags_off
    name_len = PLAYER_NAME_LEN if name_len is None else name_len

    # Все нужные поля лежат в начале структуры (префикс ~0x130 байт), поэтому
    # читаем их ОДНИМ ReadProcessMemory вместо ~30 отдельных: дешевле и поля
    # не «разъезжаются» между вызовами.
    hi = name_off + name_len
    for spec in fields.values():
        hi = max(hi, spec["off"] + struct.calcsize(_TYPE_FMT[spec["type"]]))
    hi = max(hi, flags_off + 4)

    blob = read_bytes(handle, base, hi)

    if blob is None:
        # запасной путь: поля по одному (регион не прочитан целиком)
        out = {"base": base}
        for key, spec in fields.items():
            out[key] = read_value(handle, base + spec["off"], spec["type"])
        flags = read_value(handle, base + flags_off, "u32")
        out["IsExists"] = None if flags is None else (flags >> PLAYER_ISEXISTS_BIT) & 1
        raw = read_bytes(handle, base + name_off, name_len) or b""
        out["name"] = raw.split(b"\x00", 1)[0].decode("cp1251", "replace")
        return out

    out = {"base": base}
    for key, spec in fields.items():
        out[key] = unpack_value(blob, spec["off"], spec["type"])
    flags = unpack_value(blob, flags_off, "u32")
    out["IsExists"] = None if flags is None else (flags >> PLAYER_ISEXISTS_BIT) & 1
    out["name"] = blob[name_off:name_off + name_len].split(b"\x00", 1)[0].decode("cp1251", "replace")
    return out


# ----------------------------------------------------------------------------
# Вывод
# ----------------------------------------------------------------------------

GMOD_DATA_DEFAULT = r"d:\SteamLibrary\steamapps\common\GarrysMod\garrysmod\data\d1bridge"


def atomic_write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    # GMod может держать файл открытым в момент переименования -> WinError 5.
    # Пробуем атомарно, при отказе доступа — пишем напрямую.
    for _ in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    try:
        os.remove(tmp)
    except OSError:
        pass


def die(msg, code=1):
    print("[!] " + msg, file=sys.stderr)
    sys.exit(code)


# ----------------------------------------------------------------------------
# Команды
# ----------------------------------------------------------------------------

def cmd_info(args):
    pid = find_pid(args.exe)
    if not pid:
        die(f"Процесс '{args.exe}' не найден. Запустите игру (и войдите в игру, не в меню).")
    h = open_process(pid)
    if not h:
        die("Не удалось открыть процесс. Запустите от имени администратора.")

    mods = list_modules(pid)
    main = next((m for m in mods if m["name"].lower() == args.exe.lower()), None)
    if main is None and mods:
        main = mods[0]

    wow = wintypes.BOOL(0)
    k32.IsWow64Process(h, ctypes.byref(wow))

    info = {
        "reader": "d1reader.py",
        "ts": time.time(),
        "exe": args.exe,
        "pid": pid,
        "target_is_wow64_32bit": bool(wow.value),
        "module": None if not main else {
            "name": main["name"], "base": hex(main["base"]), "size": main["size"],
        },
        "modules_count": len(mods),
    }
    out = args.out or os.path.join(GMOD_DATA_DEFAULT, "snapshot.json")
    atomic_write_json(out, info)
    k32.CloseHandle(h)

    print(f"[+] PID: {pid}")
    if main:
        print(f"[+] Модуль: {main['name']} base={hex(main['base'])} size={hex(main['size'])}")
    print(f"[+] Цель 32-битная (WOW64): {bool(wow.value)}")
    print(f"[+] Записано: {out}")


def cmd_bootstrap(args):
    if not args.name:
        die("Укажите имя героя: --name \"...\"")
    pid = find_pid(args.exe)
    if not pid:
        die(f"Процесс '{args.exe}' не найден.")
    h = open_process(pid)
    if not h:
        die("Не удалось открыть процесс. Запустите от администратора.")

    mods = list_modules(pid)
    main = next((m for m in mods if m["name"].lower() == args.exe.lower()), None)
    if main is None and mods:
        main = mods[0]
    if main is None:
        die("Не найден главный модуль процесса.")
    mod_base = main["base"]
    mod_size = main["size"]

    name_bytes = args.name.encode("cp1251")
    layout = load_empirical_layout()
    print(f"[*] Ищу имя '{args.name}' в памяти (PID {pid}) ...")
    hits = scan_all(h, name_bytes)
    print(f"[*] Найдено вхождений: {len(hits)}")

    candidates = []
    for hit in hits:
        base = hit - layout["name_off"]
        if base <= 0:
            continue
        ok, score, info = validate_player(h, base, name_bytes, layout=layout)
        if ok:
            candidates.append((score, base, info, hit))

    if not candidates:
        print("[!] Валидных структур игрока не найдено.")
        print("    Убедитесь, что герой в игре (не в главном меню), имя точное по регистру.")
        k32.CloseHandle(h)
        return

    candidates.sort(key=lambda x: -x[0])
    print("[+] Кандидаты (score, base):")
    for score, base, info, hit in candidates[:5]:
        print(f"    score={score} base={hex(base)} name_hit={hex(hit)} "
              f"Row={info.get('Row')} Col={info.get('Col')} Lvl={info.get('CharLevel')} "
              f"HP={info.get('CurLife')}/{info.get('MaxCurLife')} Gold={info.get('TotalGold')}")

    best_score, best_base, best_info, _ = candidates[0]
    print(f"[*] Беру основной кандидат: base={hex(best_base)} (score={best_score})")

    # Ищем статический указатель Players в модуле.
    print("[*] Ищу статический указатель Players в модуле ...")
    found_ptr = find_players_ptr(h, mod_base, mod_size, best_base)

    out = args.offsets or os.path.join(os.path.dirname(os.path.abspath(__file__)), "offsets.json")

    # ВАЖНО: раскладка полей в запущенной сборке отличается от клона (см. docs/13).
    # Поэтому сохраняем эмпирические смещения из существующей offsets.json,
    # а обновляем только адрес базы / указатель / имя.
    prev = {}
    if os.path.exists(out):
        try:
            with open(out, "r", encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}

    offsets = dict(prev)
    offsets["module"] = main["name"]
    offsets["module_base_hint"] = hex(mod_base)
    offsets["player_struct_size"] = PLAYER_SIZE
    offsets["player_index"] = None
    offsets["players_ptr_rva"] = None
    offsets["player_base_now"] = hex(best_base)
    offsets["player_name"] = best_info.get("name") or prev.get("player_name")
    # Смещения полей / name_off / flags_off / name_len берём из прежней карты,
    # если она была; иначе (первый запуск) — из клона.
    offsets.setdefault("fields", {k: {"off": v["off"], "type": v["type"]}
                                  for k, v in PLAYER_FIELDS.items()})
    offsets.setdefault("name_off", PLAYER_NAME_OFF)
    offsets.setdefault("flags_off", PLAYER_FLAGS_OFF)
    offsets.setdefault("name_len", PLAYER_NAME_LEN)

    if found_ptr:
        ptr_addr, arr_base, index = found_ptr
        rva = ptr_addr - mod_base
        offsets["players_ptr_rva"] = rva
        offsets["player_index"] = index
        print(f"[+] Найден указатель Players: addr={hex(ptr_addr)} rva={hex(rva)} "
              f"index={index} arr_base={hex(arr_base)}")
    else:
        print("[!] Статический указатель не найден (возможно, Players на куче без статической ссылки).")
        print("    Тогда будем использовать player_base_now (адрес изменится после перезапуска!).")
        offsets["player_base_now"] = hex(best_base)

    atomic_write_json(out, offsets)
    print(f"[+] Записано: {out}")

    snap = read_player(h, best_base, fields=offsets["fields"],
                       name_off=offsets["name_off"], flags_off=offsets["flags_off"],
                       name_len=offsets["name_len"])
    print("[+] Текущее состояние:")
    for k in ["name", "CharLevel", "CurLife", "MaxCurLife", "CurMana", "MaxCurMana",
              "TotalGold", "Row", "Col", "dir", "dungeon"]:
        print(f"    {k} = {snap.get(k)}")

    snap_path = args.out or os.path.join(GMOD_DATA_DEFAULT, "snapshot.json")
    atomic_write_json(snap_path, {"reader": "d1reader.py", "ts": time.time(),
                                  "pid": pid, "player": snap})
    print(f"[+] Snapshot: {snap_path}")
    k32.CloseHandle(h)


def cmd_autofind(args):
    pid = find_pid(args.exe)
    if not pid:
        die(f"Процесс '{args.exe}' не найден.")
    h = open_process(pid)
    if not h:
        die("Не удалось открыть процесс. Запустите от администратора.")

    mods = list_modules(pid)
    main = next((m for m in mods if m["name"].lower() == args.exe.lower()), None)
    if main is None and mods:
        main = mods[0]
    if main is None:
        die("Не найден главный модуль процесса.")
    mod_base = main["base"]
    mod_size = main["size"]

    print(f"[*] Авто-поиск игрока в куче (PID {pid}) ... это может занять пару секунд")
    cands = find_player_candidates(h)
    print(f"[*] Кандидатов, похожих на игрока: {len(cands)}")
    if not cands:
        print("[!] Ничего не найдено. Герой точно в игре (не в главном меню)?")
        k32.CloseHandle(h)
        return

    for c in cands[:10]:
        print(f"    base={hex(c['base'])} score={c['score']} name='{c['name']}' "
              f"Lvl={c['CharLevel']} HP={c['CurLife']}/{c['MaxCurLife']} "
              f"Row={c['Row']} Col={c['Col']}")

    print("[*] Собираю указатели из записываемых данных модуля ...")
    dwords = collect_module_pointers(h, mod_base, mod_size)
    chosen = None
    found_ptr = None
    for c in cands:
        for idx in range(0, 5):
            key = c["base"] - idx * PLAYER_SIZE
            if key in dwords:
                chosen, found_ptr = c, (dwords[key], key, idx)
                break
        if chosen:
            break
    if chosen is None:
        chosen = cands[0]
        print("[!] Ни у одного кандидата нет статического указателя — беру лучший по эвристике.")
    best = chosen
    print(f"[*] Основной кандидат: name='{best['name']}' base={hex(best['base'])}")

    out = args.offsets or os.path.join(os.path.dirname(os.path.abspath(__file__)), "offsets.json")

    # Сохраняем эмпирическую раскладку из прежней offsets.json (см. docs/13):
    # смещения запущенной сборки отличаются от клона на +4 (префикс) / -1 (хвост).
    prev = {}
    if os.path.exists(out):
        try:
            with open(out, "r", encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}

    offsets = dict(prev)
    offsets["module"] = main["name"]
    offsets["module_base_hint"] = hex(mod_base)
    offsets["player_struct_size"] = PLAYER_SIZE
    offsets["player_index"] = None
    offsets["players_ptr_rva"] = None
    offsets["player_base_now"] = hex(best["base"])
    offsets["player_name"] = best["name"]
    offsets.setdefault("fields", {k: {"off": v["off"], "type": v["type"]}
                                  for k, v in PLAYER_FIELDS.items()})
    offsets.setdefault("name_off", PLAYER_NAME_OFF)
    offsets.setdefault("flags_off", PLAYER_FLAGS_OFF)
    offsets.setdefault("name_len", PLAYER_NAME_LEN)

    if found_ptr:
        ptr_addr, arr_base, index = found_ptr
        rva = ptr_addr - mod_base
        offsets["players_ptr_rva"] = rva
        offsets["player_index"] = index
        print(f"[+] Найден указатель Players: addr={hex(ptr_addr)} rva={hex(rva)} "
              f"index={index} arr_base={hex(arr_base)}")
    else:
        print("[!] Статический указатель не найден — используем player_base_now "
              "(адрес может измениться после перезапуска игры).")

    atomic_write_json(out, offsets)
    print(f"[+] Записано: {out}")

    snap = read_player(h, best["base"], fields=offsets["fields"],
                       name_off=offsets["name_off"], flags_off=offsets["flags_off"],
                       name_len=offsets["name_len"])
    snap_path = args.out or os.path.join(GMOD_DATA_DEFAULT, "snapshot.json")
    atomic_write_json(snap_path, {"reader": "d1reader.py", "ts": time.time(),
                                  "pid": pid, "player": snap})
    print(f"[+] Snapshot: {snap_path}")
    k32.CloseHandle(h)


def load_offsets(path):
    if not os.path.exists(path):
        die(f"Нет файла {path}. Сначала выполните: bootstrap --name \"ИмяГероя\"")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_LAST_SEQ = {"seq": -1, "ts": -1, "sid": None}
_LAST_ACK = {"text": None, "ts": None}
_LAST_PLAYER = {"pos": None}

# Геометрия экрана TH4 (измерена кликами 16.10.2026, см. docs/15).
# Клетка, стоящая на (dRow, dCol) от героя, рисуется в точке:
#     px = cx + (dRow - dCol) * TILE_W/2
#     py = cy + ANCHOR_DY + (dRow + dCol) * TILE_H/2
# где (cx, cy) — центр клиентской области. Важно: герой нарисован НЕ в центре
# окна, а на ANCHOR_DY пикселей выше (при 2560x1440 это 64 px вверх).
SCREEN_GEOM = {"tile_w": 128, "tile_h": 64, "anchor_dy": -64}

# Экранные направления -> (dRow, dCol). Проверено 8 из 8 (docs/15).
STEP_DIRS = {
    "up": (-1, -1), "up-right": (0, -1), "right": (+1, -1), "down-right": (+1, 0),
    "down": (+1, +1), "down-left": (0, +1), "left": (-1, +1), "up-left": (-1, 0),
}
# Синонимы для WASD-подобного ввода (Y вниз, как на экране).
STEP_ALIASES = {"w": "up", "s": "down", "a": "left", "d": "right",
                "q": "up-left", "e": "up-right", "z": "down-left", "c": "down-right",
                "upleft": "up-left", "upright": "up-right",
                "downleft": "down-left", "downright": "down-right"}


def set_last_player(player):
    """Запоминает текущую клетку героя — нужна для перевода «куда идти» в пиксели
    и для решения «герой идёт или стоит» (удержание)."""
    if player:
        _LAST_PLAYER["pos"] = (player.get("Row"), player.get("Col"))
        note_player_motion(player)


def _do_move(cmd, pid, action, seq, no_clicks):
    """Команда движения в клетках -> клик в экранную точку."""
    pos = _LAST_PLAYER["pos"]
    if not pos or pos[0] is None or pos[1] is None:
        return f"{action} FAILED: позиция героя неизвестна seq={seq}"

    drow = dcol = None
    if cmd.get("row") is not None and cmd.get("col") is not None:
        drow = int(cmd["row"]) - pos[0]
        dcol = int(cmd["col"]) - pos[1]
    elif cmd.get("dir"):
        name = str(cmd["dir"]).strip().lower()
        name = STEP_ALIASES.get(name, name)
        if name not in STEP_DIRS:
            return (f"{action} FAILED: неизвестное направление '{cmd['dir']}' "
                    f"(доступно: {', '.join(STEP_DIRS)}) seq={seq}")
        drow, dcol = STEP_DIRS[name]
    else:
        drow = int(cmd.get("drow", 0))
        dcol = int(cmd.get("dcol", 0))

    target = (pos[0] + drow, pos[1] + dcol)
    try:
        n = max(1, min(16, int(cmd.get("n", 1))))       # «на N клеток»
    except Exception:
        n = 1
    if n != 1:
        drow, dcol = drow * n, dcol * n
        target = (pos[0] + drow, pos[1] + dcol)
    if drow == 0 and dcol == 0:
        return f"{action}: герой уже в ({pos[0]},{pos[1]}) seq={seq}"

    ok, info = _click_cells(pid, pos, drow, dcol, real=bool(cmd.get("real", False)),
                            no_clicks=no_clicks, tag=action,
                            quick=bool(cmd.get("quick", False)))
    if ok is None:                      # --no-clicks: подробный текст уже есть
        return info
    return (f"{action} {'OK' if ok else 'FAILED'}: ({pos[0]},{pos[1]}) -> "
            f"{target} [{drow:+d},{dcol:+d}] {info} seq={seq}")


def _click_cells(pid, pos, drow, dcol, real=False, no_clicks=False, tag="click",
                 quick=False):
    """Клик в клетку (pos + сдвиг). Возвращает (ok, текст); ok=None при --no-clicks."""
    try:
        import thclick
        hwnd, _ = thclick.find_game_window(pid)
        if not hwnd:
            return False, "окно TH4 не найдено"
        cw, ch = thclick.client_size(hwnd)
        if cw <= 0 or ch <= 0:
            return False, "размер окна неизвестен"
        g = SCREEN_GEOM
        px = cw / 2.0 + (drow - dcol) * g["tile_w"] / 2.0
        py = ch / 2.0 + g["anchor_dy"] + (drow + dcol) * g["tile_h"] / 2.0
        if no_clicks:
            return None, (f"{tag} IGNORED (--no-clicks): ({pos[0]},{pos[1]}) -> "
                          f"({pos[0] + drow},{pos[1] + dcol}) = px({px:.0f},{py:.0f})")
        ok, info = thclick.click_norm(hwnd, px / cw, py / ch, real=real, quick=quick)
        return ok, info
    except Exception as e:
        return False, f"ошибка ввода: {e}"


# ---------------------------------------------------------------------------
# «Удержание» как СОСТОЯНИЕ, а не поток команд.
#
# Каждая команда дёргает системный курсор (TH4 читает позицию именно с него),
# а клики во время ходьбы игра всё равно игнорирует. Значит посылать шаги
# пачкой бессмысленно — и неприятно: курсор в GMod прыгает постоянно.
#
# Теперь GMod шлёт {"action":"hold","dir":...} один раз при нажатии и
# {"action":"hold","dir":null} при отпускании, а reader сам кликает, только
# когда герой стоит. Дёрганье — примерно раз на отрезок ходьбы.
# ---------------------------------------------------------------------------
_HOLD = {"dir": None, "n": 4, "real": False, "last_click": 0.0, "clicks": 0,
         "clicked_at": 0.0, "click_pos": None, "blocked": False, "quick": False}
# Герой считается идущим, если клетка менялась меньше HOLD_SETTLE секунд назад.
_MOTION = {"pos": None, "changed_at": 0.0}
HOLD_SETTLE = 0.25      # столько клетка должна стоять, чтобы считать, что герой остановился
HOLD_MIN_GAP = 0.9      # минимальный интервал между кликами удержания, с
HOLD_BLOCKED = 1.6      # если после клика герой не сдвинулся столько — путь перекрыт


def note_player_motion(player, now=None):
    """Отмечает, менялась ли клетка героя: по этому решаем, можно ли кликать."""
    if not player:
        return
    pos = (player.get("Row"), player.get("Col"))
    if pos[0] is None:
        return
    if pos != _MOTION["pos"]:
        _MOTION["pos"] = pos
        _MOTION["changed_at"] = now if now is not None else time.time()
        if pos != _HOLD.get("click_pos"):
            _HOLD["blocked"] = False       # герой двинулся — снова можно идти


def hold_start(cmd, seq):
    """GMod нажал клавишу: запоминаем направление, первый клик — сразу."""
    if not cmd.get("dir"):
        _HOLD["dir"] = None
        _HOLD["blocked"] = False
        _HOLD["started_at"] = 0.0
        return "hold off (герой дойдёт сам)"
    name = str(cmd["dir"]).strip().lower()
    name = STEP_ALIASES.get(name, name)
    if name not in STEP_DIRS:
        return f"hold FAILED: неизвестное направление '{cmd['dir']}' seq={seq}"
    try:
        n = max(1, min(16, int(cmd.get("n", 4))))
    except Exception:
        n = 4
    now = time.time()
    _HOLD.update({"dir": name, "n": n, "real": bool(cmd.get("real", False)),
                  "last_click": now - HOLD_MIN_GAP, "clicks": 0,
                  "blocked": False, "started_at": now,
                  "quick": bool(cmd.get("quick", False))})
    # Базовая точка отсчёта: герой может стоять минуту до нажатия, и без неё
    # «перекрыто» срабатывало бы мгновенно (now - changed_at огромно).
    _MOTION["changed_at"] = now
    return f"hold {name} x{n} seq={seq}"


def hold_tick(pid, no_clicks=False):
    """Кликает в направлении удержания, только если герой стоит и путь свободен.

    Политика сознательно простая: клик не чаще HOLD_MIN_GAP, пока герой идёт —
    не кликаем, а если после клика герой не сдвинулся за HOLD_BLOCKED — считаем,
    что путь перекрыт, и ПЕРЕСТАЁМ кликать (иначе курсор дёргается вхолостую).
    """
    if not _HOLD["dir"]:
        return None
    now = time.time()
    if _HOLD["blocked"]:
        return None
    pos = _LAST_PLAYER["pos"]
    if not pos or pos[0] is None:
        return None
    # Отсчёт ведём от более позднего: последнее движение или начало удержания
    last_move = max(_MOTION["changed_at"], _HOLD.get("started_at") or 0.0)
    if now - last_move < HOLD_SETTLE:      # только что нажали или герой идёт
        return None

    # Путь перекрыт: герой не двигается дольше HOLD_BLOCKED, хотя удержание
    # активно. Сверяемся с последним ИЗМЕНЕНИЕМ клетки, а не со временем
    # клика (иначе каждый новый клик сбрасывал бы этот отсчёт).
    if now - last_move >= HOLD_BLOCKED:
        _HOLD["blocked"] = True
        _LAST_ACK["text"] = (f"hold {_HOLD['dir']}: путь перекрыт в ({pos[0]},{pos[1]}) — "
                             f"кликать больше не буду, пока не отпустишь клавишу")
        _LAST_ACK["ts"] = now
        _LAST_ACK["rx_ts"] = now
        print(f"[hold] {_LAST_ACK['text']}", flush=True)
        return _LAST_ACK["text"]

    if now - _HOLD["last_click"] < HOLD_MIN_GAP:
        return None

    drow, dcol = STEP_DIRS[_HOLD["dir"]]
    drow, dcol = drow * _HOLD["n"], dcol * _HOLD["n"]
    _HOLD["last_click"] = now
    _HOLD["clicked_at"] = now
    _HOLD["click_pos"] = pos
    _HOLD["clicks"] += 1
    ok, info = _click_cells(pid, pos, drow, dcol, real=_HOLD["real"],
                            no_clicks=no_clicks, tag="hold", quick=_HOLD["quick"])
    verdict = "IGNORED (--no-clicks)" if ok is None else ("OK" if ok else f"FAILED: {info}")
    _LAST_ACK["text"] = (f"hold {_HOLD['dir']} x{_HOLD['n']}: "
                         f"({pos[0]},{pos[1]}) -> ({pos[0]+drow},{pos[1]+dcol}) "
                         f"[{drow:+d},{dcol:+d}] клик #{_HOLD['clicks']} "
                         f"{'[быстро]' if _HOLD['quick'] else ''} {verdict}")
    _LAST_ACK["ts"] = now
    _LAST_ACK["rx_ts"] = now
    print(f"[hold] {_LAST_ACK['text']}", flush=True)
    return _LAST_ACK["text"]


def get_last_ack():
    """Последний ответ на команду (липнет, чтобы GMod успевал прочитать)."""
    return dict(_LAST_ACK)


def poll_command(cmd_path, pid, no_clicks=False):
    """Читает команду из GMod и исполняет её. Возвращает ack (str) или None.

    Формат команды (bridge_cmd.json):
        {"action":"click","x":0.5,"y":0.5,"real":true}  — клик в точку окна (0..1)
        {"action":"step","dir":"right"}                 — шаг на 1 клетку
        {"action":"step","drow":2,"dcol":0}              — сдвиг на N клеток
        {"action":"goto","row":50,"col":87}              — идти в клетку
        {"action":"ping"}                                — проверка связи
    во всех командах дополнительно: seq, ts, sid.

    Геометрию экрана знает только reader (SCREEN_GEOM), поэтому GMod о
    перемещениях думает в клетках, а не в пикселях.

    Дедупликация по ts (монотонное время), а не по seq: счётчик seq в GMod
    сбрасывается при перезапуске, ts — нет. sid — идентификатор сессии GMod:
    смена sid означает рестарт и сбрасывает состояние дедупа.
    """
    try:
        with open(cmd_path, "r", encoding="utf-8") as f:
            cmd = json.load(f)
    except Exception:
        return None

    seq = cmd.get("seq")
    ts = cmd.get("ts")
    sid = cmd.get("sid")
    if sid is not None and sid != _LAST_SEQ["sid"]:
        # новая сессия GMod (перезапуск): сбрасываем дедуп, иначе SysTime
        # в новой сессии меньше старого значения и команды не проходят
        _LAST_SEQ.update({"seq": -1, "ts": -1, "sid": sid})
    if ts is None:
        # старый формат без ts — дедуп по seq
        if seq is None or seq == _LAST_SEQ["seq"]:
            return None
        _LAST_SEQ["seq"] = seq
    else:
        if ts <= _LAST_SEQ["ts"]:
            return None
        _LAST_SEQ["ts"] = ts
        _LAST_SEQ["seq"] = seq

    rx_ts = time.time()       # метка для замера задержки «команда -> исполнение»

    action = (cmd.get("action") or "").lower()
    if action == "ping":
        ack = f"pong seq={seq}"
    elif action == "click":
        if no_clicks:
            ack = f"click IGNORED (--no-clicks) seq={seq}"
        else:
            try:
                import thclick
                hwnd, area = thclick.find_game_window(pid)
                if not hwnd:
                    ack = f"click FAILED: окно TH4 не найдено seq={seq}"
                else:
                    nx = float(cmd.get("x", 0.5))
                    ny = float(cmd.get("y", 0.5))
                    ok, info = thclick.click_norm(hwnd, nx, ny,
                                                  real=bool(cmd.get("real", False)))
                    ack = f"click {'OK' if ok else 'FAILED'}: {info} seq={seq}"
            except Exception as e:
                ack = f"click ERROR: {e} seq={seq}"
    elif action in ("step", "goto", "move"):
        ack = _do_move(cmd, pid, action, seq, no_clicks)
    elif action == "hold":
        ack = hold_start(cmd, seq)
    else:
        ack = f"unknown action '{action}' seq={seq}"

    _LAST_ACK["text"] = ack
    _LAST_ACK["ts"] = time.time()
    _LAST_ACK["rx_ts"] = rx_ts          # когда команда была подхвачена reader'ом
    print(f"[cmd] {ack}", flush=True)
    return ack


def cmd_watch(args):
    off_path = args.offsets or os.path.join(os.path.dirname(os.path.abspath(__file__)), "offsets.json")
    offsets = load_offsets(off_path)
    pid = find_pid(args.exe)
    if not pid:
        die(f"Процесс '{args.exe}' не найден.")
    h = open_process(pid)
    if not h:
        die("Не удалось открыть процесс. Запустите от администратора.")

    mods = list_modules(pid)
    main = next((m for m in mods if m["name"].lower() == args.exe.lower()), None)
    if main is None and mods:
        main = mods[0]
    mod_base = main["base"]

    out = args.out or os.path.join(GMOD_DATA_DEFAULT, "snapshot.json")

    rva = offsets.get("players_ptr_rva")
    index = offsets.get("player_index", 0)
    size = offsets.get("player_struct_size", PLAYER_SIZE)
    fallback_base = offsets.get("player_base_now")
    fields = offsets.get("fields")
    name_off = offsets.get("name_off", PLAYER_NAME_OFF)
    flags_off = offsets.get("flags_off", PLAYER_FLAGS_OFF)
    name_len = offsets.get("name_len", PLAYER_NAME_LEN)
    layout = {"name_off": name_off, "flags_off": flags_off,
              "off": {k: v["off"] for k, v in (fields or PLAYER_FIELDS).items()}}

    known_name = offsets.get("player_name")
    bad_streak = 0

    tick = max(0.005, args.tick)          # период опроса команд
    last_snap = 0.0
    n = 0
    print(f"[*] watch: pid={pid} -> {out} (Ctrl+C для выхода); "
          f"снимок {1.0 / max(1e-3, args.interval):.1f} Гц, команды {1.0 / tick:.0f} Гц")
    try:
        while True:
            # --- обратный канал: команды из GMod (клик-фолбэк, Р-8) --------
            # Опросим на каждом тике: задержка ввода не должна зависеть от
            # частоты записи снимка (иначе управление «плавает» на 5 Гц).
            if args.cmd:
                poll_command(args.cmd, pid, args.no_clicks)
                # «удержание»: кликаем сами, только когда герой стоит — так
                # системный курсор дёргается в разы реже, а ходьба ровнее
                hold_tick(pid, args.no_clicks)

            now = time.time()
            if now - last_snap >= args.interval:
                last_snap = now
                if rva is not None:
                    ptr = read_value(h, mod_base + rva, "u32")
                    player_base = (ptr + (index or 0) * size) if ptr else None
                else:
                    player_base = int(fallback_base, 16) if fallback_base else None

                snap = {"reader": "d1reader.py", "ts": now, "pid": pid,
                        "reader_pid": os.getpid(),
                        "ok": player_base is not None}
                player = read_player(h, player_base, fields=fields,
                                     name_off=name_off, flags_off=flags_off,
                                     name_len=name_len) if player_base else None
                if player:
                    snap["player"] = player
                    set_last_player(player)

                # --- авто-восстановление: база протухла (рестарт игры) ---------
                # Структура валидна, если есть имя, разумный уровень и живая
                # жизнь. Флаг IsExists может не стоять — не rely на него.
                valid = bool(player and player.get("name")
                             and (player.get("CharLevel") or 0) > 0
                             and (player.get("MaxCurLife") or 0) > 0)
                if not valid:
                    bad_streak += 1
                    if bad_streak >= 25 and known_name and rva is None:
                        print("[!] Структура по сохранённому адресу невалидна — ищу героя заново...")
                        try:
                            cands = find_player_candidates(handle=h, layout=layout)
                            for c in cands:
                                if c["name"].strip().lower() == known_name.strip().lower():
                                    fallback_base = hex(c["base"])
                                    player_base = c["base"]
                                    offsets["player_base_now"] = fallback_base
                                    offsets["player_name"] = c["name"]
                                    atomic_write_json(off_path, offsets)
                                    print(f"[+] Герой найден заново: base={fallback_base} "
                                          f"Lvl={c['CharLevel']} HP={c['CurLife']}/{c['MaxCurLife']}")
                                    player = read_player(h, player_base, fields=fields,
                                                         name_off=name_off, flags_off=flags_off,
                                                         name_len=name_len)
                                    snap["player"] = player
                                    snap["ok"] = True
                                    valid = True
                                    break
                        except Exception as e:
                            print(f"[!] Автопоиск не удался: {e}")
                        bad_streak = 0
                else:
                    bad_streak = 0

                snap["hold"] = {"dir": _HOLD["dir"], "n": _HOLD["n"],
                                "clicks": _HOLD["clicks"], "blocked": _HOLD["blocked"],
                                "since": (round(now - _HOLD["last_click"], 2)
                                          if _HOLD["last_click"] else None)}

                # ack липнет в каждом снимке, а не только в кадре отправки
                la = get_last_ack()
                if la["text"]:
                    snap["ack"] = la["text"]
                    snap["ack_ts"] = la["ts"]
                    snap["ack_rx_ts"] = la.get("rx_ts")

                atomic_write_json(out, snap)
                n += 1
                if args.verbose:
                    p = snap.get("player", {})
                    print(f"[{n}] Lvl={p.get('CharLevel')} HP={p.get('CurLife')}/{p.get('MaxCurLife')} "
                          f"Gold={p.get('TotalGold')} Row={p.get('Row')} Col={p.get('Col')} "
                          f"dungeon={p.get('dungeon')}")
            time.sleep(tick)
    except KeyboardInterrupt:
        print("\n[*] Остановлено.")
    finally:
        k32.CloseHandle(h)


def cmd_hexdump(args):
    pid = find_pid(args.exe)
    if not pid:
        die(f"Процесс '{args.exe}' не найден.")
    h = open_process(pid)
    if not h:
        die("Не удалось открыть процесс.")
    addr = int(args.addr, 0)
    data = read_bytes(h, addr, args.size)
    k32.CloseHandle(h)
    if data is None:
        die("Не удалось прочитать память по адресу.")
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hexs = " ".join(f"{b:02X}" for b in chunk)
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"{addr + i:08X}  {hexs:<47}  {txt}")


# ----------------------------------------------------------------------------
# Скан по значению (мини-"Cheat Engine"): scan -> narrow
# ----------------------------------------------------------------------------

SCAN_TYPES = {
    "i8": "<b", "u8": "<B", "i16": "<h", "u16": "<H",
    "i32": "<i", "u32": "<I", "i64": "<q", "u64": "<Q", "f32": "<f",
}

SCAN_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan.json")


def _iter_readable_chunks(handle, chunk=8 * 1024 * 1024):
    for base, size, mbi in iter_regions(handle):
        if not is_readable(mbi) or size == 0:
            continue
        off = 0
        while off < size:
            n = min(chunk, size - off)
            data = read_bytes(handle, base + off, n)
            if data is not None:
                yield base + off, data
            off += n


def cmd_scan(args):
    pid = find_pid(args.exe)
    if not pid:
        die(f"Процесс '{args.exe}' не найден.")
    h = open_process(pid)
    if not h:
        die("Не удалось открыть процесс. Запустите от имени администратора.")
    fmt = SCAN_TYPES[args.type]
    width = struct.calcsize(fmt)
    pat = struct.pack(fmt, args.value)
    addrs = []
    for addr, data in _iter_readable_chunks(h):
        s = 0
        while True:
            i = data.find(pat, s)
            if i < 0:
                break
            a = addr + i
            if args.align <= 1 or a % args.align == 0:
                addrs.append(a)
            s = i + 1
    k32.CloseHandle(h)
    out = args.out or SCAN_DEFAULT
    atomic_write_json(out, {"type": args.type, "value": args.value,
                            "width": width, "align": args.align, "addrs": addrs})
    print(f"[+] Найдено {len(addrs)} совпадений (type={args.type}, value={args.value})")
    for a in addrs[:args.show]:
        print(f"    {hex(a)}")
    print(f"[+] Записано: {out}")


def cmd_narrow(args):
    off = args.input or SCAN_DEFAULT
    if not os.path.exists(off):
        die(f"Нет файла {off}. Сначала выполните scan.")
    with open(off, "r", encoding="utf-8") as f:
        state = json.load(f)
    pid = find_pid(args.exe)
    if not pid:
        die(f"Процесс '{args.exe}' не найден.")
    h = open_process(pid)
    if not h:
        die("Не удалось открыть процесс.")
    fmt = SCAN_TYPES[state["type"]]
    width = struct.calcsize(fmt)
    keep = []
    for a in state["addrs"]:
        data = read_bytes(h, a, width)
        if data is None:
            continue
        if struct.unpack(fmt, data)[0] == args.value:
            keep.append(a)
    k32.CloseHandle(h)
    state["value"] = args.value
    before = len(state["addrs"])
    state["addrs"] = keep
    out = args.out or off
    atomic_write_json(out, state)
    print(f"[+] Осталось {len(keep)} адресов со значением {args.value} (было {before}). Файл: {out}")
    for a in keep[:args.show]:
        print(f"    {hex(a)}")


def cmd_readat(args):
    """Прочитать структуру игрока, если известен адрес поля CurLife (base = addr - 0xEC)."""
    pid = find_pid(args.exe)
    if not pid:
        die(f"Процесс '{args.exe}' не найден.")
    h = open_process(pid)
    if not h:
        die("Не удалось открыть процесс.")
    addr = int(args.addr, 0)
    base = addr - args.hp_off
    print(f"[*] base = {hex(base)} (addr {hex(addr)} - 0x{args.hp_off:X})")
    snap = read_player(h, base)
    for k, v in snap.items():
        print(f"    {k} = {v}")
    k32.CloseHandle(h)


# ----------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Минимальный reader памяти TH4 (только чтение)")
    p.add_argument("--exe", default=TH4_EXE, help="имя процесса (по умолчанию %s)" % TH4_EXE)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("info", help="информация о процессе и модуле")
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("bootstrap", help="найти структуру игрока и создать offsets.json")
    sp.add_argument("--name", required=True, help="имя героя")
    sp.add_argument("--offsets", default=None)
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_bootstrap)

    sp = sub.add_parser("autofind", help="авто-поиск игрока без имени и создание offsets.json")
    sp.add_argument("--offsets", default=None)
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_autofind)

    sp = sub.add_parser("watch", help="читать значения и писать snapshot.json")
    sp.add_argument("--offsets", default=None)
    sp.add_argument("--out", default=None)
    sp.add_argument("--interval", type=float, default=0.2, help="период снимка в секундах")
    sp.add_argument("--tick", type=float, default=0.02,
                    help="период опроса команд из GMod (отзывчивость ввода)")
    sp.add_argument("--verbose", action="store_true")
    sp.add_argument("--cmd", default=os.path.join(GMOD_DATA_DEFAULT, "bridge_cmd.json"),
                    help="файл команд из GMod (обратный канал); '' — отключить")
    sp.add_argument("--no-clicks", action="store_true",
                    help="не выполнять клики, только подтверждать команды")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("hexdump", help="дамп памяти по адресу")
    sp.add_argument("--addr", required=True)
    sp.add_argument("--size", type=int, default=128)
    sp.set_defaults(func=cmd_hexdump)

    sp = sub.add_parser("scan", help="найти все адреса со значением (Cheat-Engine стиль)")
    sp.add_argument("--value", type=float, required=True, help="искомое значение")
    sp.add_argument("--type", default="i32", choices=list(SCAN_TYPES.keys()))
    sp.add_argument("--align", type=int, default=1, help="выравнивание адресов (1 = любое)")
    sp.add_argument("--out", default=None)
    sp.add_argument("--show", type=int, default=20)
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("narrow", help="сузить результаты scan по новому значению")
    sp.add_argument("--value", type=float, required=True)
    sp.add_argument("--input", default=None)
    sp.add_argument("--out", default=None)
    sp.add_argument("--show", type=int, default=20)
    sp.set_defaults(func=cmd_narrow)

    sp = sub.add_parser("readat", help="прочитать структуру по адресу поля CurLife")
    sp.add_argument("--addr", required=True, help="адрес поля CurLife")
    sp.add_argument("--hp-off", type=lambda x: int(x, 0), default=0xEC,
                    help="смещение CurLife (по умолчанию 0xEC)")
    sp.set_defaults(func=cmd_readat)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
