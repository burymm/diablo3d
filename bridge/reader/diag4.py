#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diag4.py - целевой поиск живого игрока.
Ищем:
  * имя 'Iosia' (cp1251) -> base = hit - 0xA9
  * XP = 112497 (i64)     -> base = hit - 0x110
Затем для каждой базы ищем статический указатель Players в записываемых
данных модуля: значение, равное base - k*stride (stride = 0x18000 и 0x18448).
"""
import sys
from d1reader import (find_pid, open_process, list_modules, iter_regions,
                      is_readable, is_writable, read_bytes, read_value,
                      PLAYER_FIELDS, PLAYER_NAME_OFF, PLAYER_FLAGS_OFF,
                      PLAYER_ISEXISTS_BIT)

NAME = "Iosia"
XP = 112497

FIELDS = ["CharLevel", "CurLife", "MaxCurLife", "CurMana", "MaxCurMana",
          "TotalGold", "Row", "Col", "dir", "dungeon", "Xp", "ClassID"]

fd = sys.stdout


def dump_player(h, base, tag):
    name_raw = read_bytes(h, base + PLAYER_NAME_OFF, 32) or b""
    name = name_raw.split(b"\x00", 1)[0].decode("cp1251", "replace")
    flags = read_value(h, base + PLAYER_FLAGS_OFF, "u32")
    vals = {}
    for k in FIELDS:
        spec = PLAYER_FIELDS[k]
        vals[k] = read_value(h, base + spec["off"], spec["type"])
    print(f"  [{tag}] base={hex(base)} name='{name}' "
          f"IsExists={(flags >> PLAYER_ISEXISTS_BIT) & 1 if flags is not None else None}")
    print("        " + " ".join(f"{k}={vals[k]}" for k in FIELDS), file=fd)
    return vals


def main():
    pid = find_pid("TH4.exe")
    if not pid:
        print("[-] TH4.exe не найден")
        return
    h = open_process(pid)
    if not h:
        print("[-] Не удалось открыть процесс (нужны права админа)")
        return
    print(f"[*] PID {pid}")

    mods = list_modules(pid)
    main_mod = next((m for m in mods if m["name"].lower() == "th4.exe"), None)
    mod_base, mod_size = (main_mod["base"], main_mod["size"]) if main_mod else (0, 0)
    print(f"[*] Модуль base={hex(mod_base)} size={hex(mod_size)}")

    name_b = NAME.encode("cp1251")
    xp_b = XP.to_bytes(8, "little")

    print(f"[*] Ищу имя '{NAME}' ...")
    name_hits = []
    xp_hits = []
    for base, size, mbi in iter_regions(h):
        if not is_readable(mbi) or size == 0:
            continue
        data = read_bytes(h, base, size)
        if data is None:
            continue
        s = 0
        while True:
            i = data.find(name_b, s)
            if i < 0:
                break
            name_hits.append(base + i)
            s = i + 1
        s = 0
        while True:
            i = data.find(xp_b, s)
            if i < 0:
                break
            xp_hits.append(base + i)
            s = i + 1

    print(f"[*] Вхождений имени: {len(name_hits)}  вхождений XP({XP}): {len(xp_hits)}")

    cand_bases = {}
    print("[*] Кандидаты по имени (base=hit-0x%X):" % PLAYER_NAME_OFF)
    for hit in name_hits:
        b = hit - PLAYER_NAME_OFF
        v = dump_player(h, b, "name")
        if v.get("Xp") == XP or v.get("CharLevel") is not None:
            cand_bases[b] = ("name", v)
    print("[*] Кандидаты по XP (base=hit-0x110):")
    for hit in xp_hits:
        b = hit - 0x110
        v = dump_player(h, b, "xp")
        cand_bases[b] = ("xp", v)

    # Поиск статического указателя в записываемых данных модуля.
    print("[*] Собираю dwords модуля (записываемые регионы) ...")
    dwords = {}
    for base, size, mbi in iter_regions(h):
        if base < mod_base or base >= mod_base + mod_size:
            continue
        if not is_writable(mbi):
            continue
        data = read_bytes(h, base, size)
        if data is None:
            continue
        for i in range(0, len(data) - 3, 4):
            v = int.from_bytes(data[i:i + 4], "little")
            if 0x10000 <= v < 0x80000000:
                dwords.setdefault(v, []).append(base + i)
    print(f"[*] Уникальных dwords-значений в модуле: {len(dwords)}")

    strides = [0x18000, 0x18448, 0x18440, 0x18040]
    for b, (src, v) in cand_bases.items():
        found = False
        for st in strides:
            for k in range(0, 6):
                key = b - k * st
                if key in dwords:
                    print(f"[+] Указатель для base={hex(b)} ({src}): "
                          f"значение={hex(key)} k={k} stride={hex(st)} "
                          f"лежит по {[hex(a) for a in dwords[key][:3]]} "
                          f"(RVA {[hex(a - mod_base) for a in dwords[key][:3]]})")
                    found = True
        if not found:
            print(f"[!] Для base={hex(b)} ({src}) статического указателя в модуле нет")

    # Ещё: прямой поиск dword == base среди ВСЕЙ памяти (не только модуль).
    print("[*] Поиск dword==base во всей читаемой памяти ...")
    for b in cand_bases:
        pat = (b & 0xFFFFFFFF).to_bytes(4, "little")
        locs = []
        for base, size, mbi in iter_regions(h):
            if not is_readable(mbi) or size == 0:
                continue
            data = read_bytes(h, base, size)
            if data is None:
                continue
            s = 0
            while True:
                i = data.find(pat, s)
                if i < 0:
                    break
                locs.append(base + i)
                s = i + 1
        inmod = [a for a in locs if mod_base <= a < mod_base + mod_size]
        print(f"    base={hex(b)}: всего ссылок={len(locs)}  в модуле={len(inmod)}"
              + (f"  -> {[hex(x)+' (RVA '+hex(x-mod_base)+')' for x in inmod[:5]]}" if inmod else ""))


if __name__ == "__main__":
    main()
