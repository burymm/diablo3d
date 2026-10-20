#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""findpos.py - найти смещения Row/Col: что меняется при ходьбе."""
import sys
import time
from d1reader import find_pid, open_process, read_bytes

BASE = 0xDE7988
LEN = 0x200


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    pid = find_pid("TH4.exe")
    h = open_process(pid)
    a = read_bytes(h, BASE, LEN)
    if a is None:
        print("[!] не читается")
        return
    print(f"[*] base={hex(BASE)}; ХОДИ по клеткам {secs:.0f} c ...")
    print("[*] Текущие i16 в 0..120 (любое выравнивание):")
    cand = []
    for off in range(0, LEN - 1):
        v = int.from_bytes(a[off:off + 2], "little", signed=True)
        if 0 < v <= 120:
            cand.append((off, v))
    print("    " + " ".join(f"0x{o:X}:{v}" for o, v in cand))

    time.sleep(secs)
    b = read_bytes(h, BASE, LEN)
    print("[*] Изменения i16 при ходьбе (любое выравнивание):")
    for off in range(0, LEN - 1):
        va = int.from_bytes(a[off:off + 2], "little", signed=True)
        vb = int.from_bytes(b[off:off + 2], "little", signed=True)
        if va != vb:
            mark = "  <== small" if (0 <= vb <= 120) else ""
            print(f"    0x{off:03X}: {va} -> {vb}{mark}")


if __name__ == "__main__":
    main()
