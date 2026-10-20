"""
d1map_check.py — проверка данных карты из shared memory
Запуск: python d1map_check.py
"""
import sys
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d1shm_reader import D1ShmReader

r = D1ShmReader()
if not r.open():
    print("FAIL: shared memory недоступна")
    sys.exit(1)

s = r.read()
if not s:
    print("FAIL: не удалось прочитать состояние")
    sys.exit(1)

p = s['player']
fine = s['map']['FineMap']
tbw = s['map']['TileBlockWalking']
players = s['map']['PlayerMap']

print(f"Герой: {p['name']} Row={p['Row']} Col={p['Col']} dungeon={p['dungeon']}")
print(f"Размер FineMap: {len(fine)} (ожидается {112*112})")
print(f"Размер TBW: {len(tbw)} (ожидается 2049)")
print(f"Размер PlayerMap: {len(players)} (ожидается {112*112})")

# Статистика по тайлам
cnt = Counter(fine)
print(f"\nУникальных тайлов: {len(cnt)}")
print("Топ-10 тайлов:")
for tile, n in cnt.most_common(10):
    print(f"   тайл {tile:5d}: {n:6d} клеток ({n*100//len(fine):3d}%)")

# Статистика по стенам
w = Counter(tbw)
print(f"\nTileBlockWalking: значений {len(w)}")
for v, n in w.most_common(6):
    label = "проходимо" if v == 0 else f"блок {v}"
    print(f"   {label:12s}: {n:5d}")

# Клетки вокруг героя
# В TH4 стена определяется как TileBlockWalking[FineMap[row][col]]
# (индексация по ID тайла, не по клетке!)
print(f"\nКарта 7x7 вокруг героя (Row={p['Row']}, Col={p['Col']}):")
print("  'H' = герой, '#' = стена, 'T' = тайл, '.' = пусто, ' ' = вне карты")
for dr in range(-3, 4):
    row = []
    for dc in range(-3, 4):
        rr, cc = p['Row'] + dr, p['Col'] + dc
        if not (0 <= rr < 112 and 0 <= cc < 112):
            row.append(' ')
            continue
        idx = rr * 112 + cc
        tile = fine[idx]
        if rr == p['Row'] and cc == p['Col']:
            row.append('H')
        elif tile != 0 and tbw[tile] != 0:
            row.append('#')
        elif tile != 0:
            row.append('T')
        else:
            row.append('.')
    print("   " + ''.join(row))

# Сколько клеток — стены
walls = sum(1 for i in range(112 * 112) if fine[i] != 0 and tbw[fine[i]] != 0)
floors = sum(1 for i in range(112 * 112) if fine[i] != 0 and tbw[fine[i]] == 0)
print(f"\nПо всей карте 112x112: полов {floors}, стен {walls}")

r.close()
