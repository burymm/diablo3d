#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
findhero.py — диагностика: найти живой Player по ИЗВЕСТНОМУ ЗНАЧЕНИЮ.

Зачем: поиск по имени героя находит в том числе слоты сохранений и записи
героя в других структурах (у них поля нулевые). Надёжнее искать по значению,
которое игрок точно знает: уровень, HP, золото.

Идея: сканируем приватную кучу на i16 == уровень. Для каждого вхождения ищем
рядом (в окне) строку имени героя. Дельта (имя - уровень) даёт настоящие
смещения, дальше печатаем остальные поля для проверки.

Пример:
    python findhero.py --name Iosia --level 18
    python findhero.py --name Iosia --level 18 --hp 220 --gold 5000
"""
import argparse
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import d1reader as r  # noqa: E402
from d1reader import TH4_EXE  # noqa: E402

WINDOW_BEFORE = 0x200   # искать имя на это смещение назад от уровня
WINDOW_AFTER = 0x200    # ... и вперёд


def fmt_i16(v):
    return f"{v}"


def scan_i16(handle, value, chunk=8 * 1024 * 1024, overlap=0x10):
    """Все адреса, где лежит int16 == value (в приватной куче)."""
    pat = struct.pack("<h", value)
    out = []
    for base, size, mbi in r.iter_regions(handle):
        if not r.is_readable(mbi) or mbi.Type != r.MEM_PRIVATE or size == 0:
            continue
        off = 0
        while off < size:
            n = min(chunk, size - off)
            data = r.read_bytes(handle, base + off, n)
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
    for base, size, mbi in r.iter_regions(handle):
        if not r.is_readable(mbi) or mbi.Type != r.MEM_PRIVATE or size == 0:
            continue
        off = 0
        while off < size:
            n = min(chunk, size - off)
            data = r.read_bytes(handle, base + off, n)
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


def read_at(handle, addr, size):
    return r.read_bytes(handle, addr, size)


def probe(handle, name_addr, layout):
    """Печатает поля под адресом name_addr по раскладке layout."""
    f = layout["off"]
    noff = layout["name_off"]

    def g(key, typ):
        return r.read_value(handle, name_addr - noff + f[key], typ)

    return {
        "base": name_addr - noff,
        "Row": g("Row", "i16"), "Col": g("Col", "i16"),
        "dir": g("dir", "i8"), "CharLevel": g("CharLevel", "i16"),
        "CurLife": g("CurLife", "i32"), "MaxCurLife": g("MaxCurLife", "i32"),
        "CurMana": g("CurMana", "i32"), "MaxCurMana": g("MaxCurMana", "i32"),
        "TotalGold": g("TotalGold", "i32"), "Xp": g("Xp", "i64"),
        "ClassID": g("ClassID", "i8"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default=None,
                    help="имя героя как в игре (по умолчанию — из offsets.json)")
    ap.add_argument("--level", type=int, default=None, help="уровень героя (i16)")
    ap.add_argument("--hp", type=int, default=None, help="текущее HP как в игре (будет *64)")
    ap.add_argument("--gold", type=int, default=None, help="золото как в игре")
    ap.add_argument("--apply", action="store_true",
                    help="записать найденный base в offsets.json (смещения не трогаем)")
    ap.add_argument("--exe", default=None)
    args = ap.parse_args()

    # Имя по умолчанию — из offsets.json; exe — из константы d1reader
    if args.exe is None:
        args.exe = TH4_EXE
    if args.name is None:
        layout0 = r.load_empirical_layout()
        args.name = layout0.get("player_name")
        if not args.name:
            print("[!] Имя героя не задано и не найдено в offsets.json.")
            print("    Запусти: python findhero.py --name ИмяГероя")
            return 1
        print(f"[*] Имя героя из offsets.json: {args.name}")

    pid = r.find_pid(args.exe)
    if not pid:
        print(f"[!] Процесс {args.exe} не найден")
        return 1
    h = r.open_process(pid)
    if not h:
        print("[!] Не удалось открыть процесс (нужны права администратора)")
        return 1

    name_bytes = args.name.encode("cp1251")
    layout = r.load_empirical_layout()

    print(f"[*] PID={pid}")
    print(f"[*] Ищу имя '{args.name}' ...")
    name_hits = scan_name(h, name_bytes)
    print(f"[*] Вхождений имени: {len(name_hits)}")
    for a in name_hits:
        print(f"      {a:#010x}")

    def score_cand(delta, info):
        s = 0
        if info["CharLevel"] == args.level:
            s += 4
        if args.hp is not None:
            exp = args.hp * 64
            if info["CurLife"] == exp:
                s += 5
            elif info["MaxCurLife"] == exp:
                s += 3
        if info["CurLife"] and info["CurLife"] > 0:
            s += 2
        if info["CurMana"] and info["MaxCurMana"] and info["MaxCurMana"] > 0:
            s += 2
        if (0 <= (info["Row"] or -1) <= 111) and (0 <= (info["Col"] or -1) <= 111):
            s += 2
        if delta == (layout["off"]["CharLevel"] - layout["name_off"]):
            s += 2   # дельта совпадает с рабочей раскладкой -> это настоящий Player
        return s

    found = []
    if args.level is not None:
        print(f"[*] Ищу уровень {args.level} (int16) в куче ...")
        lvl_hits = scan_i16(h, args.level)
        print(f"[*] Вхождений уровня: {len(lvl_hits)}")
        seen = set()
        for laddr in lvl_hits:
            lo = laddr - WINDOW_BEFORE
            hi = laddr + WINDOW_AFTER
            blob = read_at(h, lo, hi - lo)
            if blob is None:
                continue
            i = blob.find(name_bytes)
            if i < 0:
                continue
            naddr = lo + i
            if naddr in seen:
                continue
            seen.add(naddr)
            delta = naddr - laddr          # имя минус уровень
            info = probe(h, naddr, layout)
            found.append((score_cand(delta, info), laddr, naddr, delta, info))

    if not found:
        print()
        print("[!] Структура не найдена по (уровень + имя).")
        print("    Проверь уровень и что герой реально в игре.")
        r.k32.CloseHandle(h)
        return 1

    found.sort(key=lambda t: -t[0])
    print()
    print("=== Кандидаты (отсортированы по правдоподобности) ===")
    for sc, laddr, naddr, delta, info in found:
        base = naddr - layout["name_off"]
        lvl_ok = "OK" if info["CharLevel"] == args.level else "!!"
        print(f"  score={sc:2d}  base={base:#010x}  имя@{naddr:#010x}  delta={delta:+d}")
        print(f"      Lvl={info['CharLevel']}{lvl_ok}  HP={info['CurLife']}/{info['MaxCurLife']} "
              f"({(info['CurLife'] or 0)/64:.0f}/{(info['MaxCurLife'] or 0)/64:.0f} HP)  "
              f"Mana={info['CurMana']}/{info['MaxCurMana']}  Gold={info['TotalGold']}  "
              f"Row={info['Row']} Col={info['Col']} Class={info['ClassID']}")

    best_sc, best_laddr, best_naddr, best_delta, best_info = found[0]
    best_base = best_naddr - layout["name_off"]

    print()
    print(f"[*] ЛУЧШИЙ кандидат: base={best_base:#x} (score={best_sc})")
    expected_delta = layout["off"]["CharLevel"] - layout["name_off"]
    if best_delta != expected_delta:
        print(f"[!] ВНИМАНИЕ: delta={best_delta}, а рабочая раскладка даёт {expected_delta}.")
        print(f"    Значит смещения CharLevel/name уехали. CharLevel_off = "
              f"{layout['name_off'] + best_delta} (0x{layout['name_off'] + best_delta:x})")
    else:
        print(f"[+] delta совпадает с рабочей раскладкой ({expected_delta:#x}) — "
              f"смещения верные, менять их НЕ нужно.")

    if args.apply:
        off_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "offsets.json")
        with open(off_path, "r", encoding="utf-8") as f:
            off = json.load(f)
        off["player_base_now"] = hex(best_base)
        off["player_name"] = args.name
        tmp = off_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(off, f, ensure_ascii=False, indent=2)
        os.replace(tmp, off_path)
        print(f"[+] Записал player_base_now={off['player_base_now']} в {off_path}")
    else:
        print("[*] Чтобы применить, повтори с ключом --apply")

    r.k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())