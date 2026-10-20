#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
findtbw_code.py — поиск TileBlockWalking через код-референсы.

Ищет в машинном коде TH4.exe инструкции, которые обращаются к TileBlockWalking,
и вытаскивает адрес TBW из операнда.

В исходниках Item.cpp:6134 есть:
    return TileBlockWalking[ FineMap[row][col] ] == 0;

Это компилируется в инструкцию вида:
    movzx eax, byte ptr [reg + offset]  ; где reg содержит адрес TBW
    или
    cmp byte ptr [reg + offset], 0

Ищем характерные последовательности байт, соответствующие этим инструкциям.
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

# Размер TBW
TBW_SIZE = 2049

# Адрес FineMap (из предыдущего сканирования)
FINEMAP_ADDR = 0x2b1b000


def find_tbw_via_code_refs(handle, mod_base, mod_size):
    """Ищет TBW через код-референсы в машинном коде."""
    lo, hi = mod_base, mod_base + mod_size
    
    print(f"[*] Ищем код-референсы в диапазоне {hex(lo)}..{hex(hi)}")
    
    # В исходниках FineMap=0x005F5BB0, TBW=0x0060B2E0
    # Разница: 0x60B2E0 - 0x5F5BB0 = 0x15730
    # Но в запущенной сборке адреса другие
    
    # Ищем инструкции, которые загружают адрес TBW
    # Например: lea reg, [offset] или mov reg, [offset]
    
    # Характерные последовательности байт для инструкций:
    # movzx eax, byte ptr [reg + offset]  ->  0F B6 40 xx  или  0F B6 41 xx  и т.д.
    # cmp byte ptr [reg + offset], 0     ->  80 38 00  или  80 39 00  и т.д.
    
    # Но проще искать по относительному смещению от FineMap
    # В исходниках: TBW - FineMap = 0x15730
    
    # Давайте поищем все регионы, где есть 2049 байт с значениями 0..10
    # и проверим, что они соответствуют ожидаемой структуре TBW
    
    candidates = []
    
    for base, size, mbi in iter_regions(handle):
        if base < lo or base >= hi:
            continue
        if not is_readable(mbi):
            continue
        if size < TBW_SIZE:
            continue
        
        data = read_bytes(handle, base, TBW_SIZE)
        if data is None:
            continue
        
        ok = True
        for i in range(TBW_SIZE):
            v = data[i]
            if v > 10:
                ok = False
                break
        if not ok:
            continue
        
        # Проверяем соотношение стен и проходимых клеток
        zeros = sum(1 for b in data if b == 0)
        nonzeros = TBW_SIZE - zeros
        
        # Настоящий TBW: минимум 10% стен и минимум 10% проходимых
        if nonzeros < 205 or zeros < 205:
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
    
    # Ищем TBW через код-референсы
    candidates = find_tbw_via_code_refs(h, 0x1400000, 0x1000000)
    
    if not candidates:
        print("[!] TileBlockWalking не найден")
        sys.exit(1)
    
    print(f"\n[+] Найдено кандидатов: {len(candidates)}")
    for base, zeros, nonzeros in candidates:
        print(f"    {hex(base)}: zeros={zeros}, nonzeros={nonzeros}")
    
    k32.CloseHandle(h)


if __name__ == "__main__":
    main()
