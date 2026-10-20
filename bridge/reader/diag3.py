# -*- coding: utf-8 -*-
"""Диагностика: ищем статический указатель Players в данных модуля."""
import re
import d1reader as R

RUN = re.compile(rb"[\x20-\x7e]{2,31}\x00")


def main():
    pid = R.find_pid("TH4.exe")
    h = R.open_process(pid)
    mods = R.list_modules(pid)
    m = next((x for x in mods if x["name"].lower() == "th4.exe"), mods[0])
    mb, ms = m["base"], m["size"]
    print(f"module {m['name']} {hex(mb)}+{hex(ms)}")

    regions = [(b, s, mt, prot) for b, s, mm in R.iter_regions(h)
               for mt, prot in [(mm.Type, mm.Protect)]]

    # 1) множество dword'ов из записываемых регионов модуля
    dwords = {}
    wbytes = 0
    for base, size, mbi in R.iter_regions(h):
        if base < mb or base >= mb + ms or not R.is_writable(mbi):
            continue
        data = R.read_bytes(h, base, size)
        if data is None:
            continue
        wbytes += len(data)
        for i in range(0, len(data) - 3, 4):
            v = int.from_bytes(data[i:i + 4], "little")
            if 0x10000 <= v < 0x80000000:
                dwords.setdefault(v, base + i)
    print(f"writable module bytes: {hex(wbytes)}, unique pointers: {len(dwords)}")

    # 2) релаксированный поиск структур игрока
    cands = []
    seen = set()
    for base, size, mbi in R.iter_regions(h):
        if not R.is_readable(mbi) or mbi.Type != R.MEM_PRIVATE or size == 0:
            continue
        off = 0
        while off < size:
            n = min(8 * 1024 * 1024, size - off)
            data = R.read_bytes(h, base + off, n)
            if data is None:
                break
            for mm in RUN.finditer(data):
                co = mm.start() - 0xA9
                if co < 0 or co + 0x130 > len(data):
                    continue
                sb = base + off + co
                flags = int.from_bytes(data[co + 0xA4:co + 0xA8], "little")
                if not ((flags >> 3) & 1):
                    continue
                row = int.from_bytes(data[co + 0x2E:co + 0x30], "little", signed=True)
                col = int.from_bytes(data[co + 0x30:co + 0x32], "little", signed=True)
                if not (0 <= row <= 111 and 0 <= col <= 111):
                    continue
                lvl = int.from_bytes(data[co + 0x10C:co + 0x10E], "little", signed=True)
                if not (1 <= lvl <= 99):
                    continue
                life = int.from_bytes(data[co + 0xEC:co + 0xF0], "little", signed=True)
                mlife = int.from_bytes(data[co + 0xF0:co + 0xF4], "little", signed=True)
                if not (0 < mlife <= 10_000_000 and 0 <= life <= mlife):
                    continue
                if sb in seen:
                    continue
                seen.add(sb)
                cands.append((sb, mm.group()[:-1], row, col, lvl, life, mlife))
            if n <= 0x200:
                break
            off += n - 0x200
    print(f"relaxed candidates: {len(cands)}")
    for c in cands[:15]:
        print("   ", hex(c[0]), c[1], "row", c[2], "col", c[3], "lvl", c[4],
              "life", c[5], mlife := c[6])

    # 3) у кого есть статический указатель (с учётом индекса в массиве)
    print("--- candidates with a static pointer in module ---")
    found = 0
    for sb, name_b, row, col, lvl, life, mlife in cands:
        for idx in range(0, 5):
            key = sb - idx * R.PLAYER_SIZE
            if key in dwords:
                print(f"    base={hex(sb)} name={name_b!r} idx={idx} "
                      f"ptr@{hex(dwords[key])} -> {hex(key)}")
                found += 1
                break
    print("with static pointer:", found)
    R.k32.CloseHandle(h)


if __name__ == "__main__":
    main()
