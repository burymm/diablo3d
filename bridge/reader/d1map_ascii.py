"""
d1map_ascii.py — ASCII-карта уровня из shared memory
Запуск: python d1map_ascii.py [радиус]
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d1shm_reader import D1ShmReader

RADIUS = int(sys.argv[1]) if len(sys.argv) > 1 else 20

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

print(f"Герой: {p['name']} R{p['Row']} C{p['Col']} dungeon={p['dungeon']}")
print()

# Считаем статистику
walls = 0
floors = 0
empty = 0
for i in range(112 * 112):
    t = fine[i]
    if t == 0:
        empty += 1
    elif tbw[t] != 0:
        walls += 1
    else:
        floors += 1

total = 112 * 112
print(f"Вся карта 112x112: пол {floors} ({floors*100//total}%), "
      f"стены {walls} ({walls*100//total}%), пусто {empty} ({empty*100//total}%)")
print()

# Область вокруг героя
R, C = p['Row'], p['Col']
print(f"Область {R-RADIUS}..{R+RADIUS} x {C-RADIUS}..{C+RADIUS}:")
print("  # = стена, . = пол, ' ' = пусто, H = герой, P = монстр/игрок")
for dr in range(-RADIUS, RADIUS + 1):
    row = []
    for dc in range(-RADIUS, RADIUS + 1):
        rr, cc = R + dr, C + dc
        if not (0 <= rr < 112 and 0 <= cc < 112):
            row.append(' ')
            continue
        idx = rr * 112 + cc
        if rr == R and cc == C:
            row.append('H')
        elif players[idx] != 0:
            row.append('P')
        elif fine[idx] == 0:
            row.append(' ')
        elif tbw[fine[idx]] != 0:
            row.append('#')
        else:
            row.append('.')
    print("  " + ''.join(row))

r.close()
