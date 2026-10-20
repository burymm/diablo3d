#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scanmap.py — сканирование памяти TH4 для поиска FineMap/TileBlockWalking.

Цель: найти карту уровня (112×112 клеток) в памяти запущенной игры,
прочитать, какие клетки проходимы, и сохранить результат в map.json.

Использование:
  python scanmap.py --name "Iosia" --level 18
  python scanmap.py --autofind
  python scanmap.py --finemap 0x5F5BB0 --tbw 0x60B2E0  # ручные адреса
"""

import sys
import os
import json
import struct
import argparse
import time

# Импортируем функции из d1reader
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d1reader import (
    find_pid, open_process, list_modules, read_bytes, read_value,
    iter_regions, is_readable, is_writable,
    load_empirical_layout, find_player_candidates, validate_player,
    read_player, PLAYER_NAME_OFF, PLAYER_FLAGS_OFF,
    PLAYER_NAME_LEN, atomic_write_json, GMOD_DATA_DEFAULT,
    k32, MEM_PRIVATE, TH4_EXE, TH4_GAME_DIR, D1MAP_EXPORT, load_d1map_export,
)

FINE_MAP_SIZE = 112 * 112  # количество клеток
FINE_MAP_BYTES = FINE_MAP_SIZE * 4  # размер в байтах (int32)

# Адреса из исходников (dataseg.cpp) — для запущенной сборки могут не совпадать
FINEMAP_ADDR_HINT = 0x005F5BB0
TBW_ADDR_HINT = 0x0060B2E0  # TileBlockWalking

WINDOW_BEFORE = 0x200   # искать имя на это смещение назад от уровня
WINDOW_AFTER = 0x200    # ... и вперёд


def scan_i16(handle, value, chunk=8 * 1024 * 1024, overlap=0x10):
    """Все адреса, где лежит int16 == value (в приватной куче)."""
    pat = struct.pack("<h", value)
    out = []
    for base, size, mbi in iter_regions(handle):
        if not is_readable(mbi) or mbi.Type != MEM_PRIVATE or size == 0:
            continue
        off = 0
        while off < size:
            n = min(chunk, size - off)
            data = read_bytes(handle, base + off, n)
            if data is None:
                break
            start = 0
            while True:
                i = data.find(pat, start)
                if i < 0:
                    break
                out.append(base + off + i)
                start = i + 1
            if n <= overlap:
                break
            off += n - overlap
    return out


def scan_name(handle, name_bytes, chunk=8 * 1024 * 1024, overlap=0x40):
    out = []
    for base, size, mbi in iter_regions(handle):
        if not is_readable(mbi) or mbi.Type != MEM_PRIVATE or size == 0:
            continue
        off = 0
        while off < size:
            n = min(chunk, size - off)
            data = read_bytes(handle, base + off, n)
            if data is None:
                break
            start = 0
            while True:
                i = data.find(name_bytes, start)
                if i < 0:
                    break
                out.append(base + off + i)
                start = i + 1
            if n <= overlap:
                break
            off += n - overlap
    return out


def find_hero_by_level(handle, name_bytes, level, layout):
    """Ищет героя по уровню (i16) + имя в окне. Возвращает (base, info) или (None, None)."""
    print(f"[*] Ищу уровень {level} (int16) в куче ...")
    lvl_hits = scan_i16(handle, level)
    print(f"[*] Вхождений уровня: {len(lvl_hits)}")
    
    f = layout["off"]
    noff = layout["name_off"]
    expected_delta = f["CharLevel"] - noff
    
    found = []
    seen = set()
    for laddr in lvl_hits:
        lo = laddr - WINDOW_BEFORE
        hi = laddr + WINDOW_AFTER
        blob = read_bytes(handle, lo, hi - lo)
        if blob is None:
            continue
        i = blob.find(name_bytes)
        if i < 0:
            continue
        naddr = lo + i
        if naddr in seen:
            continue
        seen.add(naddr)
        delta = naddr - laddr
        
        # Читаем поля
        base = naddr - noff
        info = {"base": base}
        for key, typ in [("Row", "i16"), ("Col", "i16"), ("dir", "i8"),
                         ("CharLevel", "i16"), ("CurLife", "i32"), ("MaxCurLife", "i32"),
                         ("CurMana", "i32"), ("MaxCurMana", "i32"),
                         ("TotalGold", "i32"), ("ClassID", "i8")]:
            info[key] = read_value(handle, base + f[key], typ)
        
        # Скоринг
        score = 0
        if info["CharLevel"] == level:
            score += 4
        if info["CurLife"] and info["CurLife"] > 0:
            score += 2
        if info["CurMana"] and info["MaxCurMana"] and info["MaxCurMana"] > 0:
            score += 2
        if (0 <= (info["Row"] or -1) <= 111) and (0 <= (info["Col"] or -1) <= 111):
            score += 2
        if delta == expected_delta:
            score += 2
        
        found.append((score, base, delta, info))
    
    if not found:
        return None, None
    
    found.sort(key=lambda t: -t[0])
    score, base, delta, info = found[0]
    return base, info


def try_read_finemap_at(handle, addr, row, col):
    """Пытается прочитать FineMap по указанному адресу. Возвращает данные или None."""
    data = read_bytes(handle, addr, FINE_MAP_BYTES)
    if data is None:
        return None

    # Проверяем, что значения похожи на индексы тайлов (0..2048)
    import random
    for _ in range(100):
        i = random.randint(0, FINE_MAP_SIZE - 1)
        v = struct.unpack_from("<i", data, i * 4)[0]
        if v < 0 or v > 2048:
            return None

    # Проверяем позицию героя — должна быть проходимой (0 или 1)
    idx = row * 112 + col
    hero_tile = struct.unpack_from("<i", data, idx * 4)[0]
    if hero_tile < 0 or hero_tile > 2:
        return None

    return data


def scan_for_finemap(handle, mod_base, mod_size, row, col):
    """Сканирует записываемые регионы модуля на паттерн FineMap.
    Возвращает список (base, hero_tile, wall_count, floor_count)."""
    lo, hi = mod_base, mod_base + mod_size
    candidates = []

    for base, size, mbi in iter_regions(handle):
        if base < lo or base >= hi:
            continue
        if not is_writable(mbi):
            continue
        if size < FINE_MAP_BYTES:
            continue

        data = read_bytes(handle, base, min(size, FINE_MAP_BYTES))
        if data is None:
            continue

        ok = True
        for i in range(200):
            v = struct.unpack_from("<i", data, i * 4)[0]
            if v < 0 or v > 2048:
                ok = False
                break
        if not ok:
            continue

        idx = row * 112 + col
        hero_tile = struct.unpack_from("<i", data, idx * 4)[0]
        if hero_tile < 0 or hero_tile > 2:
            continue

        # Считаем стены и пол в области 50x50 вокруг героя
        wall_count = 0
        floor_count = 0
        r0 = max(0, row - 25)
        r1 = min(111, row + 25)
        c0 = max(0, col - 25)
        c1 = min(111, col + 25)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                idx2 = r * 112 + c
                v = struct.unpack_from("<i", data, idx2 * 4)[0]
                if v == 0:
                    floor_count += 1
                else:
                    wall_count += 1

        candidates.append((base, hero_tile, wall_count, floor_count))

    return candidates


def try_read_tbw_at(handle, addr):
    """Пытается прочитать TileBlockWalking по указанному адресу."""
    data = read_bytes(handle, addr, 2049)
    if data is None:
        return None

    for i in range(2049):
        v = data[i]
        if v > 10:
            return None

    return data


def scan_for_tbw(handle, mod_base, mod_size, finemap_addr):
    """Сканирует ВСЕ читаемые регионы процесса на паттерн TileBlockWalking.
    TBW может быть в любом месте: модуль, DLL, куча."""
    candidates = []

    for base, size, mbi in iter_regions(handle):
        if not is_readable(mbi):
            continue
        if size < 2049:
            continue
        if finemap_addr and abs(base - finemap_addr) < 0x10000:
            continue  # слишком близко к FineMap — это не TBW

        data = read_bytes(handle, base, 2049)
        if data is None:
            continue

        ok = True
        for i in range(2049):
            v = data[i]
            if v > 10:
                ok = False
                break
        if not ok:
            continue

        # Проверяем соотношение стен и проходимых клеток
        zeros = sum(1 for b in data if b == 0)
        nonzeros = 2049 - zeros
        # Настоящий TBW: минимум 1 стен и минимум 1 проходимых
        if nonzeros < 1 or zeros < 1:
            continue

        candidates.append(base)

    return candidates


def build_ascii_map(finemap_data, tbw_data, row, col):
    """Строит ASCII-карту уровня вокруг героя."""
    lines = []
    r0 = max(0, row - 15)
    r1 = min(111, row + 15)
    c0 = max(0, col - 15)
    c1 = min(111, col + 15)

    for r in range(r0, r1 + 1):
        line = ""
        for c in range(c0, c1 + 1):
            idx = r * 112 + c
            tile = struct.unpack_from("<i", finemap_data, idx * 4)[0]
            if tbw_data and 0 <= tile < 2049:
                walkable = tbw_data[tile] == 0
            else:
                walkable = True

            if r == row and c == col:
                line += "@"
            elif walkable:
                line += "."
            else:
                line += "#"
        lines.append(line)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="Имя героя")
    ap.add_argument("--level", type=int, help="Уровень героя (для поиска)")
    ap.add_argument("--autofind", action="store_true", help="Автопоиск героя")
    ap.add_argument("--finemap", type=lambda x: int(x, 16), help="Адрес FineMap (hex)")
    ap.add_argument("--tbw", type=lambda x: int(x, 16), help="Адрес TileBlockWalking (hex)")
    args = ap.parse_args()

    # 1. Находим процесс
    pid = find_pid(TH4_EXE)
    if not pid:
        print(f"[!] Процесс {TH4_EXE} не найден. Запусти: bridge\\reader\\run_th43d.bat")
        sys.exit(1)

    h = open_process(pid)
    if not h:
        print("[!] Не удалось открыть процесс. Запустите от администратора.")
        sys.exit(1)

    mods = list_modules(pid)
    main_mod = next((m for m in mods if m["name"].lower() == TH4_EXE.lower()), None)
    if main_mod is None and mods:
        main_mod = mods[0]
    if main_mod is None:
        print("[!] Не найден главный модуль.")
        sys.exit(1)

    mod_base = main_mod["base"]
    mod_size = main_mod["size"]
    print(f"[+] PID: {pid}, модуль: {main_mod['name']} base={hex(mod_base)}")

    # 2. Берём игрока из сохранённого адреса (offsets.json)
    layout = load_empirical_layout()
    f = layout["off"]
    noff = layout["name_off"]
    
    saved_base = layout.get("player_base_now")
    if not saved_base:
        print("[!] player_base_now не найден в offsets.json")
        print("    Запусти: python findhero.py --name Iosia --level 24 --apply")
        sys.exit(1)
    
    saved_base = int(saved_base, 16) if isinstance(saved_base, str) else saved_base
    
    # Читаем поля напрямую
    row_v = read_value(h, saved_base + f["Row"], "i16")
    col_v = read_value(h, saved_base + f["Col"], "i16")
    hp_v = read_value(h, saved_base + f["CurLife"], "i32")
    max_hp_v = read_value(h, saved_base + f["MaxCurLife"], "i32")
    level_v = read_value(h, saved_base + f["CharLevel"], "i16")
    name_v = read_bytes(h, saved_base + noff, layout.get("name_len", 32))
    
    # Проверяем, что данные осмысленные
    if not (row_v is not None and 0 <= row_v <= 111 and
        col_v is not None and 0 <= col_v <= 111 and
        hp_v is not None and hp_v > 0 and
        max_hp_v is not None and max_hp_v > 0):
        print(f"[!] Сохранённый адрес {hex(saved_base)} не прошёл проверку")
        print("    Запусти: python findhero.py --name Iosia --level 24 --apply")
        sys.exit(1)
    
    player_base = saved_base
    print(f"[+] Герой из offsets.json: {hex(player_base)}")
    print(f"    Level={level_v} Row={row_v} Col={col_v} HP={hp_v}/{max_hp_v}")

    # Читаем Row/Col из структуры
    from d1reader import PLAYER_FIELDS
    fields_for_read = {}
    for k, v in layout["off"].items():
        if isinstance(v, dict):
            off = v["off"]
            typ = v.get("type", "i32")
        else:
            off = v
            typ = PLAYER_FIELDS.get(k, {}).get("type", "i32")
        fields_for_read[k] = {"off": off, "type": typ}
    
    snap = read_player(h, player_base, fields=fields_for_read,
                       name_off=layout["name_off"], flags_off=layout["flags_off"],
                       name_len=layout.get("name_len", 32))
    row = snap.get("Row")
    col = snap.get("Col")
    print(f"[+] Герой: {snap.get('name')} Row={row} Col={col} HP={snap.get('CurLife')}/{snap.get('MaxCurLife')}")

    # 3. Ищем FineMap
    finemap_data = None
    finemap_addr = None

    # 3.0 Экспорт из инструментированной сборки — основной источник адресов
    d1map = load_d1map_export()
    exp_finemap = d1map.get("FineMap")
    exp_tbw = d1map.get("TileBlockWalking")

    if exp_finemap and not args.finemap:
        print(f"[*] FineMap из {D1MAP_EXPORT}: {hex(exp_finemap)}")
        finemap_data = try_read_finemap_at(h, exp_finemap, row, col)
        if finemap_data:
            finemap_addr = exp_finemap
            print("[+] FineMap подтверждён по адресу из экспорта!")
        else:
            print("[!] Адрес из экспорта не прошёл проверку (другой запуск?) — сканирую")

    if args.finemap:
        print(f"[*] Пробую FineMap по адресу {hex(args.finemap)}...")
        finemap_data = try_read_finemap_at(h, args.finemap, row, col)
        if finemap_data:
            finemap_addr = args.finemap
            print("[+] FineMap найден по указанному адресу!")
    elif finemap_data is None:
        print(f"[*] Пробую FineMap по адресу из исходников {hex(FINEMAP_ADDR_HINT)}...")
        finemap_data = try_read_finemap_at(h, FINEMAP_ADDR_HINT, row, col)
        if finemap_data:
            finemap_addr = FINEMAP_ADDR_HINT
            print("[+] FineMap найден по адресу из исходников!")

    if finemap_data is None:
        print("[*] Сканирую записываемые регионы на паттерн FineMap (112x112 int)...")
        t0 = time.time()
        candidates = scan_for_finemap(h, mod_base, mod_size, row, col)
        print(f"[*] Найдено кандидатов: {len(candidates)} (за {time.time()-t0:.1f}с)")

        if candidates:
            # Выбираем кандидата, где есть и стены, и проходимые клетки
            best = None
            for base, hero_tile, wall_count, floor_count in candidates:
                if wall_count > 100 and floor_count > 100:
                    best = (base, hero_tile, wall_count, floor_count)
                    break
            if best is None:
                # Берём того, у кого больше стен
                candidates.sort(key=lambda x: -x[2])
                best = candidates[0]
            finemap_addr, hero_tile, wall_count, floor_count = best
            finemap_data = read_bytes(h, finemap_addr, FINE_MAP_BYTES)
            print(f"[+] FineMap: {hex(finemap_addr)} (hero_tile={hero_tile}, walls={wall_count}, floor={floor_count})")

    if finemap_data is None:
        print("[!] FineMap не найден.")
        sys.exit(1)

    # 4. Ищем TileBlockWalking
    tbw_data = None
    tbw_addr = None

    # 4.0 Экспорт из инструментированной сборки — основной источник
    if exp_tbw and not args.tbw:
        print(f"[*] TileBlockWalking из {D1MAP_EXPORT}: {hex(exp_tbw)}")
        tbw_data = try_read_tbw_at(h, exp_tbw)
        if tbw_data:
            tbw_addr = exp_tbw
            print("[+] TileBlockWalking подтверждён по адресу из экспорта!")
        else:
            print("[!] Адрес из экспорта не прошёл проверку — сканирую")

    if args.tbw:
        print(f"[*] Пробую TileBlockWalking по адресу {hex(args.tbw)}...")
        tbw_data = try_read_tbw_at(h, args.tbw)
        if tbw_data:
            tbw_addr = args.tbw
            print("[+] TileBlockWalking найден!")
    elif tbw_data is None:
        print(f"[*] Пробую TileBlockWalking по адресу из исходников {hex(TBW_ADDR_HINT)}...")
        tbw_data = try_read_tbw_at(h, TBW_ADDR_HINT)
        if tbw_data:
            tbw_addr = TBW_ADDR_HINT
            print("[+] TileBlockWalking найден по адресу из исходников!")

    if tbw_data is None:
        # Ищем в окрестности FineMap (в исходниках они рядом)
        print(f"[*] Ищем TileBlockWalking в окрестности FineMap ({hex(finemap_addr)})...")
        search_range = 0x10000
        lo = max(mod_base, finemap_addr - search_range)
        hi = min(mod_base + mod_size, finemap_addr + search_range)
        
        for base, size, mbi in iter_regions(h):
            if base < lo or base >= hi:
                continue
            if not is_writable(mbi):
                continue
            if size < 2049:
                continue
            if abs(base - finemap_addr) < 0x10000:
                continue  # слишком близко к FineMap
            
            data = read_bytes(h, base, 2049)
            if data is None:
                continue
            
            # Проверяем значения 0..10
            ok = True
            for i in range(2049):
                if data[i] > 10:
                    ok = False
                    break
            if not ok:
                continue
            
            # Проверяем соотношение стен и проходимых
            zeros = sum(1 for b in data if b == 0)
            nonzeros = 2049 - zeros
            if nonzeros < 200 or zeros < 200:
                continue
            
            tbw_addr = base
            tbw_data = data
            print(f"[+] TileBlockWalking: {hex(tbw_addr)} (zeros={zeros}, nonzeros={nonzeros})")
            break

    if tbw_data is None:
        print("[*] Сканирую на паттерн TileBlockWalking (2049 байт, значения 0..10)...")
        t0 = time.time()
        candidates = scan_for_tbw(h, mod_base, mod_size, finemap_addr)
        print(f"[*] Найдено кандидатов: {len(candidates)} (за {time.time()-t0:.1f}с)")

        if candidates:
            # Выводим все кандидаты для выбора
            print(f"[*] Найдено кандидатов: {len(candidates)}")
            for i, cand in enumerate(candidates):
                data = read_bytes(h, cand, 2049)
                zeros = sum(1 for b in data if b == 0)
                nonzeros = 2049 - zeros
                print(f"    [{i}] {hex(cand)}: zeros={zeros}, nonzeros={nonzeros}")
            
            # Выбираем кандидата с наибольшим количеством стен (но не мусор)
            best = None
            best_score = 0
            for cand in candidates:
                data = read_bytes(h, cand, 2049)
                zeros = sum(1 for b in data if b == 0)
                nonzeros = 2049 - zeros
                # Скоринг: чем больше ненулевых (стен), тем лучше, но не мусор
                if nonzeros > best_score and zeros > 100:
                    best_score = nonzeros
                    best = cand
            
            if best is None:
                best = candidates[0]
            
            tbw_addr = best
            tbw_data = read_bytes(h, tbw_addr, 2049)
            print(f"[+] TileBlockWalking: {hex(tbw_addr)}")
            # Диагностика: покажем первые 20 байт
            print(f"    Первые 20 байт: {list(tbw_data[:20])}")
            zeros = sum(1 for b in tbw_data if b == 0)
            nonzeros = 2049 - zeros
            print(f"    Нули: {zeros}, ненулевые: {nonzeros}")

    # 5. Выводим ASCII-карту
    print("\n[@] — герой, [.] — можно ходить, [#] — стена\n")
    ascii_map = build_ascii_map(finemap_data, tbw_data, row, col)
    print(ascii_map)

    # 6. Сохраняем в map.json
    out_path = os.path.join(GMOD_DATA_DEFAULT, "map.json")
    out = {
        "ts": time.time(),
        "player": {
            "name": snap.get("name"),
            "row": row,
            "col": col,
        },
        "finemap_addr": hex(finemap_addr) if finemap_addr else None,
        "tbw_addr": hex(tbw_addr) if tbw_addr else None,
        "map": []
    }

    for r in range(112):
        row_data = []
        for c in range(112):
            idx = r * 112 + c
            tile = struct.unpack_from("<i", finemap_data, idx * 4)[0]
            if tbw_data and 0 <= tile < 2049:
                walkable = 1 if tbw_data[tile] == 0 else 0
            else:
                walkable = 1
            row_data.append(walkable)
        out["map"].append(row_data)

    atomic_write_json(out_path, out)
    print(f"\n[+] Карта сохранена: {out_path}")

    # Сохраняем finemap_addr в offsets.json для дальнейшего использования
    off_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "offsets.json")
    try:
        with open(off_path, "r", encoding="utf-8") as f:
            off = json.load(f)
        off["finemap_addr"] = hex(finemap_addr) if finemap_addr else None
        off["player_base_now"] = hex(player_base)
        off["player_name"] = snap.get("name", "Iosia")
        tmp = off_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(off, f, ensure_ascii=False, indent=2)
        os.replace(tmp, off_path)
        print(f"[+] finemap_addr сохранён в offsets.json")
    except Exception as e:
        print(f"[!] Не удалось сохранить offsets.json: {e}")

    k32.CloseHandle(h)


if __name__ == "__main__":
    main()
