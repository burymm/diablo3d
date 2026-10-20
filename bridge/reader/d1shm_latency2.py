"""
d1shm_latency2.py — раздельный замер: принятие команды vs анимация шага
Запуск: python d1shm_latency2.py [повторов]

Метрики:
  t_accept  — команда -> TH4 начал шаг (CurAction: 0 -> != 0)
              это и есть задержка ВВОДА (то, что чувствует игрок)
  t_land    — команда -> герой реально сменил клетку (Row/Col)
              это включает анимацию шага (собственная скорость TH4)
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d1shm_reader import D1ShmReader
from d1shm_cmd import D1ShmCommand

DIRS = {5: "up", 6: "right", 7: "down", 8: "left",
        1: "up-right", 2: "up-left", 3: "down-right", 4: "down-left"}

reader = D1ShmReader()
cmd = D1ShmCommand()
if not reader.open() or not cmd.open():
    print("FAIL: shared memory недоступна")
    sys.exit(1)


def wait_idle(timeout=5.0):
    """Ждём CurAction == 0 (герой стоит и готов к шагу)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = reader.read()
        if s and s['player'].get('CurAction', 0) == 0:
            return True
        time.sleep(0.008)
    return False


REPEATS = int(sys.argv[1]) if len(sys.argv) > 1 else 6
accepts, lands = [], []

print(f"{'направление':12s} {'t_accept':>10s} {'t_land':>10s}   (мс)")
print("-" * 40)

for i in range(REPEATS):
    action = [5, 6, 7, 8, 1, 2, 3, 4][i % 8]

    if not wait_idle():
        print("  (герой не остановился, пропуск)")
        continue

    before = reader.read()
    p0 = (before['player']['Row'], before['player']['Col'])

    t0 = time.time()
    cmd.send_walk(action)

    t_accept = None
    t_land = None
    deadline = t0 + 3.0
    while time.time() < deadline:
        s = reader.read()
        if s:
            p = s['player']
            if t_accept is None and p.get('CurAction', 0) != 0:
                t_accept = (time.time() - t0) * 1000
            pos = (p['Row'], p['Col'])
            if pos != p0:
                t_land = (time.time() - t0) * 1000
                break
        time.sleep(0.004)

    if t_accept is not None:
        accepts.append(t_accept)
    if t_land is not None:
        lands.append(t_land)

    a = f"{t_accept:10.0f}" if t_accept is not None else f"{'--':>10s}"
    l = f"{t_land:10.0f}" if t_land is not None else f"{'--':>10s}"
    print(f"{DIRS[action]:12s} {a} {l}")

reader.close()
cmd.close()


def stat(name, arr):
    if not arr:
        print(f"\n{name}: нет данных")
        return
    s = sorted(arr)
    print(f"\n{name}: мин {s[0]:.0f} | медиана {s[len(s)//2]:.0f} | "
          f"макс {s[-1]:.0f} мс")


stat("Задержка ВВОДА (команда -> TH4 начал шаг)", accepts)
stat("Время до смены клетки (включая анимацию шага)", lands)
print("\nДля сравнения: клик-фолбэк давал 209-454 мс до смены клетки.")
