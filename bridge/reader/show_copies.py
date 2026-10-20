#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""show_copies.py - читаем Xp/HP/золото из известных копий и ищем живой
Player по значению опыта (i64) по всей памяти."""
import sys
from d1reader import find_pid, open_process, read_bytes, scan_all

# corrected layout for the RUNNING build (clone offset - 1 shifted)
OFF = {"flags": 0xA3, "name": 0xA8, "LightRadius": 0xA7, "ClassID": 0xC8,
       "CurStrength": 0xC9, "CurMagic": 0xCD, "CurDex": 0xD1, "CurVit": 0xD5,
       "BaseLife": 0xE3, "MaxBaseLife": 0xE7, "CurLife": 0xEB, "MaxCurLife": 0xEF,
       "BaseMana": 0xF7, "MaxBaseMana": 0xFB, "CurMana": 0xFF, "MaxCurMana": 0x103,
       "CharLevel": 0x10B, "Xp": 0x10F, "TotalGold": 0x11F}


def read_player_at(h, base, tag):
    buf = read_bytes(h, base, 0x130)
    if buf is None:
        print(f"[{tag}] {hex(base)}: не читается")
        return
    def u16(o): return int.from_bytes(buf[o:o + 2], "little", signed=False)
    def i32(o): return int.from_bytes(buf[o:o + 4], "little", signed=True)
    def i64(o): return int.from_bytes(buf[o:o + 8], "little", signed=True)
    name = buf[OFF["name"]:OFF["name"] + 32].split(b"\x00")[0].decode("latin1", "replace")
    print(f"[{tag}] base={hex(base)} name={name!r} "
          f"ClassID={buf[OFF['ClassID']]} Lvl={u16(OFF['CharLevel'])} "
          f"HP={i32(OFF['CurLife'])}/{i32(OFF['MaxCurLife'])} "
          f"Mana={i32(OFF['CurMana'])}/{i32(OFF['MaxCurMana'])} "
          f"Gold={i32(OFF['TotalGold'])} Xp={i64(OFF['Xp'])}")


def main():
    value = int(sys.argv[1]) if len(sys.argv) > 1 else 113243
    pid = find_pid("TH4.exe")
    h = open_process(pid)
    print(f"[*] PID {pid}")
    read_player_at(h, 0xDE7988, "copy1")
    read_player_at(h, 0xF692AC, "copy2")
    print(f"[*] Сканирую i64={value} по всей памяти ...")
    hits = scan_all(h, value.to_bytes(8, "little", signed=True))
    print(f"[*] Найдено {len(hits)} совпадений i64:")
    for a in hits:
        probe = a - OFF["Xp"]
        buf = read_bytes(h, probe + OFF["name"], 32)
        nm = buf.split(b"\x00")[0].decode("latin1", "replace") if buf else "?"
        print(f"    @{hex(a)}  (если поле Xp: base={hex(probe)}, name={nm!r})")


if __name__ == "__main__":
    main()
