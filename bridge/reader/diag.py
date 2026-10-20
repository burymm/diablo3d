# -*- coding: utf-8 -*-
"""Диагностика памяти: разовые проверки гипотез о layout."""
import re
import sys
import d1reader as R


def main():
    pid = R.find_pid("TH4.exe")
    h = R.open_process(pid)
    print("pid", pid, "handle", h)

    from collections import Counter
    hist = Counter()
    total = 0
    maxregions = []
    for base, size, mbi in R.iter_regions(h):
        if R.is_readable(mbi):
            hist[hex(mbi.Type)] += 1
            total += size
            maxregions.append((size, base, mbi.Type))
    print("readable bytes:", hex(total))
    print("region count by type:", dict(hist))
    maxregions.sort(reverse=True)
    print("largest regions:")
    for size, base, typ in maxregions[:12]:
        print(f"    base={hex(base)} size={hex(size)} type={hex(typ)}")

    pat = re.compile(rb"[\x20-\x7e]{2,31}\x00")
    matches = 0
    cand = 0
    shown = 0
    for base, size, mbi in R.iter_regions(h):
        if not R.is_readable(mbi):
            continue
        off = 0
        while off < size:
            n = min(8 * 1024 * 1024, size - off)
            data = R.read_bytes(h, base + off, n)
            if data is None:
                break
            for m in pat.finditer(data):
                matches += 1
                co = m.start() - 0xA9
                if co < 0 or co + 0x130 > len(data):
                    continue
                row = int.from_bytes(data[co + 0x2E:co + 0x30], "little", signed=True)
                col = int.from_bytes(data[co + 0x30:co + 0x32], "little", signed=True)
                if not (0 <= row <= 111 and 0 <= col <= 111):
                    continue
                lvl = int.from_bytes(data[co + 0x10C:co + 0x10E], "little", signed=True)
                if not (1 <= lvl <= 99):
                    continue
                cand += 1
                if shown < 25:
                    shown += 1
                    life = int.from_bytes(data[co + 0xEC:co + 0xF0], "little", signed=True)
                    mlife = int.from_bytes(data[co + 0xF0:co + 0xF4], "little", signed=True)
                    gold = int.from_bytes(data[co + 0x120:co + 0x124], "little", signed=True)
                    print(f"    {hex(base + off + co)} name={m.group()!r} "
                          f"row={row} col={col} lvl={lvl} life={life} mlife={mlife} "
                          f"gold={gold} type={hex(mbi.Type)}")
            if n <= 0x200:
                break
            off += n - 0x200

    print("regex matches:", matches, "row/col/lvl-valid:", cand)
    R.k32.CloseHandle(h)


if __name__ == "__main__":
    main()
