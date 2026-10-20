#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag7.py - сколько раз встречаются «живые» значения и где."""
import sys
from d1reader import (find_pid, open_process, list_modules, iter_regions,
                      is_readable, read_bytes)

VALUES = [
    ("gold_i32", 3627, 4),
    ("hp_i32", 3200, 4),
    ("hp_fixed_i32", 3200 * 64, 4),
    ("xp_i64", 112497, 8),
    ("mana_i32", 11228, 4),
]


def main():
    pid = find_pid("TH4.exe")
    h = open_process(pid)
    mods = list_modules(pid)
    mm = next((m for m in mods if m["name"].lower() == "th4.exe"), None)
    mb, ms = mm["base"], mm["size"]
    print(f"[*] PID {pid} module base={hex(mb)} size={hex(ms)}")

    pats = {name: (val.to_bytes(width, "little"), val, width)
            for name, val, width in VALUES}
    counts = {name: [] for name in pats}

    for base, size, mbi in iter_regions(h):
        if not is_readable(mbi) or size == 0:
            continue
        # читаем чанками по 8МБ
        off = 0
        CH = 8 * 1024 * 1024
        while off < size:
            n = min(CH, size - off)
            data = read_bytes(h, base + off, n)
            if data is None:
                off += n
                continue
            for name, (pat, val, width) in pats.items():
                s = 0
                while True:
                    i = data.find(pat, s)
                    if i < 0:
                        break
                    a = base + off + i
                    counts[name].append(a)
                    s = i + 1
            if n < CH:
                break
            off += n

    for name, addrs in counts.items():
        inmod = [a for a in addrs if mb <= a < mb + ms]
        print(f"[{name}] всего={len(addrs)}  в модуле={len(inmod)}")
        for a in addrs[:12]:
            tag = "MODULE rva=" + hex(a - mb) if mb <= a < mb + ms else "heap"
            print(f"    {hex(a)}  {tag}")


if __name__ == "__main__":
    main()
