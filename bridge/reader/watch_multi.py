#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watch_multi.py - следит за несколькими адресами-кандидатами и печатает изменения.
Запуск: python watch_multi.py [секунды]
"""
import sys
import time
from d1reader import (find_pid, open_process, read_value, read_bytes,
                      PLAYER_NAME_OFF, PLAYER_FIELDS)

BASES = {
    "live_A": 0xde7987,
    "live_B": 0xf692ab,
    "stale":  0xde7553,
}
WATCH = ["CurAction", "Row", "Col", "NextRow", "NextCol", "TargetRow", "TargetCol",
         "xOfs", "yOfs", "xVel", "yVel", "dir", "CurLife", "MaxCurLife",
         "CurMana", "MaxCurMana", "CharLevel", "Xp", "TotalGold", "dungeon"]


def snapshot(h, base):
    out = {}
    for k in WATCH:
        s = PLAYER_FIELDS[k]
        out[k] = read_value(h, base + s["off"], s["type"])
    return out


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    pid = find_pid("TH4.exe")
    h = open_process(pid)
    print(f"[*] PID {pid}; мониторю {secs:.0f} c. ДВИГАЙСЯ в игре и открывай инвентарь!")

    prev = {name: snapshot(h, b) for name, b in BASES.items()}
    for name, b in BASES.items():
        nm = read_bytes(h, b + PLAYER_NAME_OFF, 32).split(b"\x00", 1)[0]
        print(f"    {name}: base={hex(b)} name={nm.decode('cp1251', 'replace')}")

    t0 = time.time()
    changes = {k: 0 for k in BASES}
    while time.time() - t0 < secs:
        time.sleep(0.25)
        for name, b in BASES.items():
            cur = snapshot(h, b)
            diff = {k: (prev[name][k], cur[k]) for k in WATCH if prev[name][k] != cur[k]}
            if diff:
                changes[name] += 1
                print(f"[{time.time()-t0:5.1f}s] {name} {hex(b)}: " +
                      " ".join(f"{k}:{a}->{c}" for k, (a, c) in diff.items()))
                prev[name] = cur
    print("[*] Число изменений за интервал:", changes)


if __name__ == "__main__":
    main()
