#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watchfields.py - живой монитор полей-кандидатов при ходьбе."""
import sys
import time
from d1reader import find_pid, open_process, read_bytes

BASE = 0xDE7988
CANDS = [0x20, 0x24, 0x28, 0x2E, 0x30, 0x32, 0x34, 0x36, 0x38, 0x3A, 0x3C, 0x3E, 0x40, 0x42, 0x44]


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    pid = find_pid("TH4.exe")
    h = open_process(pid)
    print("[*] иди по клеткам WASD...")
    print("  t   " + "  ".join(f"{o:>4X}" for o in CANDS) + "   dir")
    t0 = time.time()
    while time.time() - t0 < secs:
        b = read_bytes(h, BASE, 0x120)
        vals = []
        for o in CANDS:
            v = int.from_bytes(b[o:o + 2], "little", signed=True)
            vals.append(v)
        d = b[0x58]
        print(f"{time.time()-t0:5.1f}  " + "  ".join(f"{v:>4}" for v in vals) + f"   {d}")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
