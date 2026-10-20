"""
d1shm_watch.py — наблюдение за позицией героя в реальном времени
Запуск: python d1shm_watch.py [секунд]
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d1shm_reader import D1ShmReader

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0

r = D1ShmReader()
if not r.open():
    print("FAIL: shared memory 'D1BridgeState' недоступна (th43d.exe запущен?)")
    sys.exit(1)

print(f"Наблюдение {SECONDS:.0f} с (интервал 0.25 с):")
prev = None
t0 = time.time()
moved = 0
while time.time() - t0 < SECONDS:
    s = r.read()
    if s:
        p = s['player']
        pos = (p['Row'], p['Col'])
        mark = ''
        if prev and pos != prev:
            mark = '  <-- ДВИЖЕНИЕ'
            moved += 1
        print(f"  t={time.time()-t0:5.2f}s  Row={p['Row']:3d} Col={p['Col']:3d}  "
              f"HP={p['CurLife']:5d}  dir={p['dir']}{mark}")
        prev = pos
    time.sleep(0.25)

r.close()
print(f"\nСдвигов позиции: {moved}")
