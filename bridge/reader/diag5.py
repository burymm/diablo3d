#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag5.py - где лежит ссылка на живого игрока и что вокруг Row/Col."""
import sys
from d1reader import (find_pid, open_process, list_modules, iter_regions,
                      is_readable, read_bytes, read_value, MEM_PRIVATE)
from ctypes import wintypes

LIVE = 0xde7987
STALE = 0xde7553
COPY = 0xf692ab


def hx(data, base):
    for i in range(0, len(data), 16):
        ch = data[i:i + 16]
        hs = " ".join(f"{b:02X}" for b in ch)
        tx = "".join(chr(b) if 32 <= b < 127 else "." for b in ch)
        print(f"  {base + i:08X}  {hs:<47}  {tx}")


def main():
    pid = find_pid("TH4.exe")
    h = open_process(pid)
    mods = list_modules(pid)
    mm = next((m for m in mods if m["name"].lower() == "th4.exe"), None)
    mb, ms = mm["base"], mm["size"]

    print(f"[*] PID {pid} module base={hex(mb)} size={hex(ms)}")

    for target in (LIVE, STALE, COPY):
        print(f"\n=== ссылки на {hex(target)} (dword) ===")
        pat = target.to_bytes(4, "little")
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
                a = base + i
                inmod = mb <= a < mb + ms
                print(f"    по {hex(a)} ({'MODULE rva=' + hex(a - mb) if inmod else 'heap/other'}, "
                      f"region={hex(base)} prot=0x{mbi.Protect:X} type=0x{mbi.Type:X})")
                s = i + 1

    print(f"\n=== hexdump живого {hex(LIVE)} (0x00..0x70) ===")
    hx(read_bytes(h, LIVE, 0x70), LIVE)
    print(f"\n=== hexdump старого {hex(STALE)} (0x00..0x70) ===")
    hx(read_bytes(h, STALE, 0x70), STALE)

    # Что лежит в модуле по адресам, где могли бы стоять глобалы Players:
    # просканируем записываемые регионы и покажем dwords, попадающие в диапазон
    # вокруг живых копий (0xde0000..0xf70000).
    print("\n=== dwords в модуле, похожие на указатели на кучи 0xde0000..0xf70000 ===")
    for base, size, mbi in iter_regions(h):
        if base < mb or base >= mb + ms:
            continue
        if mbi.Protect not in (0x04, 0x08, 0x40, 0x80):
            continue
        data = read_bytes(h, base, size)
        if data is None:
            continue
        for i in range(0, len(data) - 3, 4):
            v = int.from_bytes(data[i:i + 4], "little")
            if 0xdd0000 <= v <= 0xf80000:
                print(f"    {hex(base + i)} (rva {hex(base + i - mb)}) = {hex(v)}")


if __name__ == "__main__":
    main()
