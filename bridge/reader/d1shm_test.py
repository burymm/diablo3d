"""
d1shm_test.py — быстрый тест shared memory reader'а
Запуск: python d1shm_test.py
"""
import sys
import os
import time

# Добавляем текущую папку в path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from d1shm_reader import D1ShmReader, MAP_SIZE


def main():
    print(f"D1Bridge SHM Reader Test")
    print(f"Expected SHM size: {MAP_SIZE} bytes")
    print()

    reader = D1ShmReader()
    if not reader.open():
        print("[FAIL] Cannot open shared memory 'D1BridgeState'")
        print("  Make sure th43d.exe is running")
        return 1

    print("[OK] Shared memory opened")
    print()

    # Читаем 10 раз с интервалом 100мс
    for i in range(10):
        state = reader.read()
        if state:
            p = state['player']
            print(f"[{i+1:2d}] {p['name']:12s} | "
                  f"Row={p['Row']:3d} Col={p['Col']:3d} | "
                  f"HP={p['CurLife']:4d}/{p['MaxCurLife']:4d} | "
                  f"Mana={p['CurMana']:4d}/{p['MaxCurMana']:4d} | "
                  f"Lvl={p['CharLevel']:2d} | "
                  f"Gold={p['TotalGold']:6d} | "
                  f"Dungeon={p['dungeon']}")
        else:
            print(f"[{i+1:2d}] Read failed")
        time.sleep(0.1)

    reader.close()
    print()
    print("[OK] Test complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())
