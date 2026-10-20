#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
findtbw.py — поиск TileBlockWalking по сигнатуре.

Ищет массив из 2049 байт (uchar), где:
- 0 = можно ходить
- ненулевое = стена (WT_ALL, WT_1_WALK и т.д.)

Стратегия:
1. Находим FineMap (уже знаем адрес)
2. Ищем TBW в окрестности FineMap (в исходниках они рядом)
3. Проверяем сигнатуру: 2049 байт, значения 0..10, есть и нули, и ненулевые
"""

import sys
import os
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d1reader import (
    find_pid, open_process, read_bytes, read_value,
    iter_regions, is_readable, is_writable,
    load_empirical_layout, k32, MEM_PRIVATE,
)

TBW_SIZE = 2049


def scan_for_tbw_near_finemap(handle, finemap_addr, mod_base, mod_size):
    """Ищет TBW в окрестности FineMap."""
    # В исходниках FineMap=0x005F5BB0, TBW=0x0060B2E0, разница=0x5B30
    # Ищем в диапазоне ±0x10000 от FineMap
    search_range = 0x10000
    
    lo = max(mod_base, finemap_addr - search_range)
    hi = min(mod_base + mod_size, finemap_addr + search_range)
    
    print(f"[*] Ищем TBW в диапазоне {hex(lo)}..{hex(hi)} (FineMap={hex(finemap_addr)})")
    
    candidates = []
    
    for base, size, mbi in iter_regions(handle):
        if base < lo or base >= hi:
            continue
        if not is_writable(mbi):
            continue
        if size < TBW_SIZE:
            continue
        
        data = read_bytes(handle, base, TBW_SIZE)
        if data is None:
            continue
        
        # Проверяем значения 0..10
        ok = True
        for i in range(TBW_SIZE):
            v = data[i]
            if v > 10:
                ok = False
                break
        if not ok:
            continue
        
        # Проверяем, что есть и нули, и ненулевые
        zeros = sum(1 for b in data if b == 0)
        nonzeros = TBW_SIZE - zeros
        
        # Настоящий TBW: минимум 10% стен и минимум 10% проходимых
        if nonzeros < 200 or zeros < 200:
            continue
        
        candidates.append((base, zeros, nonzeros))
        print(f"  [+] Кандидат: {hex(base)} zeros={zeros} nonzeros={nonzeros}")
    
    return candidates


def scan_for_tbw_by_pattern(handle, mod_base, mod_size):
    """Ищет TBW по паттерну во всех записываемых регионах."""
    lo, hi = mod_base, mod_base + mod_size
    
    print(f"[*] Ищем TBW по паттерну во всех записываемых регионах...")
    
    candidates = []
    
    for base, size, mbi in iter_regions(handle):
        if base < lo or base >= hi:
            continue
        if not is_writable(mbi):
            continue
        if size < TBW_SIZE:
            continue
        
        data = read_bytes(handle, base, TBW_SIZE)
        if data is None:
            continue
        
        # Проверяем значения 0..10
        ok = True
        for i in range(TBW_SIZE):
            v = data[i]
            if v > 10:
                ok = False
                break
        if not ok:
            continue
        
        # Проверяем, что есть и нули, и ненулевые
        zeros = sum(1 for b in data if b == 0)
        nonzeros = TBW_SIZE - zeros
        
        # Настоящий TBW: минимум 10% стен и минимум 10% проходимых
        if nonzeros < 200 or zeros < 200:
            continue
        
        candidates.append((base, zeros, nonzeros))
        print(f"  [+] Кандидат: {hex(base)} zeros={zeros} nonzeros={nonzeros}")
    
    return candidates


def main():
    pid = find_pid("TH4.exe")
    if not pid:
        print("[!] Процесс TH4.exe не найден")
        sys.exit(1)
    
    h = open_process(pid)
    if not h:
        print("[!] Не удалось открыть процесс")
        sys.exit(1)
    
    layout = load_empirical_layout()
    finemap_addr = layout.get("finemap_addr")
    
    if finemap_addr:
        finemap_addr = int(finemap_addr, 16) if isinstance(finemap_addr, str) else finemap_addr
        print(f"[*] FineMap: {hex(finemap_addr)}")
        
        # Ищем рядом с FineMap
        candidates = scan_for_tbw_near_finemap(h, finemap_addr, 0x1400000, 0x1000000)
    else:
        print("[!] FineMap не найден, ищем по всему модулю")
        candidates = scan_for_tbw_by_pattern(h, 0x1400000, 0x1000000)
    
    if not candidates:
        print("[!] TileBlockWalking не найден")
        sys.exit(1)
    
    print(f"\n[+] Найдено кандидатов: {len(candidates)}")
    for base, zeros, nonzeros in candidates:
        print(f"    {hex(base)}: zeros={zeros}, nonzeros={nonzeros}")
    
    k32.CloseHandle(h)


if __name__ == "__main__":
    main()
