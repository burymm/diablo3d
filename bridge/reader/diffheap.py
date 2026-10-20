#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diffheap.py - ищем изменяющиеся dwords в куче, пока игрок двигается."""
import sys
import time
from ctypes import c_void_p
from d1reader import (find_pid, open_process, list_modules, iter_regions,
                      is_readable, is_writable, read_bytes, k32,
                      MEMORY_BASIC_INFORMATION)

SEED_ADDRS = [0xde7987, 0xde7553, 0xf692ab, 0xde9d2b]


def region_of(h, addr):
    mbi = MEMORY_BASIC_INFORMATION()
    if k32.VirtualQueryEx(h, c_void_p(addr), ctypes_byref(mbi), ctypes_sizeof(mbi)) == 0:
        return None
    return mbi


def ctypes_byref(x):
    import ctypes
    return ctypes.byref(x)


def ctypes_sizeof(x):
    import ctypes
    return ctypes.sizeof(x)


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    pid = find_pid("TH4.exe")
    h = open_process(pid)
    print(f"[*] PID {pid}")

    regions = {}
    import ctypes
    for a in SEED_ADDRS:
        mbi = MEMORY_BASIC_INFORMATION()
        if k32.VirtualQueryEx(h, c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
            continue
        key = (mbi.BaseAddress or 0, mbi.RegionSize or 0)
        regions[key] = mbi
        print(f"    {hex(a)} -> region base={hex(key[0])} size={hex(key[1])} "
              f"prot=0x{mbi.Protect:X} type=0x{mbi.Type:X}")

    snaps = {}
    for (base, size), mbi in regions.items():
        snaps[base] = read_bytes(h, base, size)
    print(f"[*] Снял снимок {len(snaps)} регионов. ДВИГАЙСЯ {secs:.0f} c ...")
    time.sleep(secs)

    total = 0
    for (base, size), mbi in regions.items():
        a = snaps[base]
        b = read_bytes(h, base, size)
        if a is None or b is None or len(a) != len(b):
            print(f"    region {hex(base)}: не перечитался")
            continue
        changed = []
        for i in range(0, size - 3, 4):
            if a[i:i + 4] != b[i:i + 4]:
                changed.append(i)
        total += len(changed)
        print(f"[reg {hex(base)} size={hex(size)}] изменённых dwords: {len(changed)}")
        for i in changed[:80]:
            va = int.from_bytes(a[i:i + 4], "little")
            vb = int.from_bytes(b[i:i + 4], "little")
            print(f"    +{hex(i)} @{hex(base+i)}: {va} -> {vb}")
    print(f"[*] Всего изменённых выравненных dwords: {total}")


if __name__ == "__main__":
    main()
