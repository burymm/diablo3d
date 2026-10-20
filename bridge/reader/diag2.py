# -*- coding: utf-8 -*-
"""Диагностика: все вхождения имени и статические указатели на них."""
import d1reader as R

NAME = b"Iosia\0"


def region_of(regions, addr):
    for base, size, mbi in regions:
        if base <= addr < base + size:
            return base, size, mbi
    return None


def main():
    pid = R.find_pid("TH4.exe")
    h = R.open_process(pid)
    print("pid", pid)

    regions = [(b, s, m) for b, s, m in R.iter_regions(h) if R.is_readable(m)]

    print("--- все вхождения имени ---")
    hits = []
    for base, size, mbi in regions:
        data = R.read_bytes(h, base, size)
        if data is None:
            continue
        start = 0
        while True:
            i = data.find(NAME, start)
            if i < 0:
                break
            hits.append(base + i)
            start = i + 1
    for a in hits:
        reg = region_of(regions, a)
        struct_base = a - 0xA9
        regb = region_of(regions, struct_base)
        print(f"    name@{hex(a)} struct_base={hex(struct_base)} "
              f"name_region={hex(reg[0])}+{hex(reg[1])} type={hex(reg[2].Type)} "
              f"base_region={hex(regb[0])}+{hex(regb[1])}")

    # ищем в модуле записываемые двойные слова, указывающие рядом с struct_base
    mods = R.list_modules(pid)
    main_mod = next((m for m in mods if m["name"].lower() == "th4.exe"), mods[0])
    mb, ms = main_mod["base"], main_mod["size"]
    print(f"--- module {main_mod['name']} {hex(mb)}+{hex(ms)} ---")

    for a in hits:
        sb = a - 0xA9
        lo, hi = sb - 0x100000, sb + 0x1000
        print(f"--- dwords in module pointing into [{hex(lo)},{hex(hi)}] (near struct_base {hex(sb)}) ---")
        found = 0
        for base, size, mbi in regions:
            if base < mb or base >= mb + ms or not R.is_writable(mbi):
                continue
            data = R.read_bytes(h, base, size)
            if data is None:
                continue
            for i in range(0, len(data) - 3, 4):
                v = int.from_bytes(data[i:i + 4], "little")
                if lo <= v <= hi:
                    print(f"    [{hex(base + i)}] -> {hex(v)}  (delta {hex(v - sb)})")
                    found += 1
                    if found > 15:
                        break
            if found > 15:
                break
        if found == 0:
            print("    (нет)")

    R.k32.CloseHandle(h)


if __name__ == "__main__":
    main()
