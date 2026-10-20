#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clicktest.py — проверка обратного канала: клик в окно TH4 -> герой идёт?

Тест сквозной: пишет команду в `bridge_cmd.json` (как это делает аддон GMod),
reader (d1reader.py watch --cmd) читает её, кликает в окно TH4, игра двигает
героя, а мы следим за `snapshot.json` — тем же файлом, который читает GMod.

Что измеряем:
  1. реагирует ли герой на клик вообще (меняются Row/Col);
  2. задержку «команда записана -> снимок показал новое положение»;
  3. сколько времени герой шёл до цели;
  4. частоту кадров снимка (верхняя граница отзывчивости управления).

Запуск (TH4 должна быть запущена, reader - работать):
    python clicktest.py --dir up --tiles 4
"""
import argparse
import json
import os
import sys
import time

try:
    import ctypes
    ctypes.WinDLL("kernel32").SetConsoleOutputCP(65001)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from d1reader import GMOD_DATA_DEFAULT, atomic_write_json
except Exception:                                                  # pragma: no cover
    GMOD_DATA_DEFAULT = r"d:\SteamLibrary\steamapps\common\GarrysMod\garrysmod\data\d1bridge"

    def atomic_write_json(path, obj):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


# Экранные направления -> (сдвиг Row, сдвиг Col) в изометрии TH4.
# Проверено калибровкой 16.10.2026 (см. docs/15): клик в центр клетки,
# стоящей в этом направлении от героя, даёт ровно этот сдвиг.
DIRS = {
    "up":         (-1, -1),
    "up-right":   (0, -1),
    "right":      (+1, -1),
    "down-right": (+1,  0),
    "down":       (+1, +1),
    "down-left":  (0, +1),
    "left":       (-1, +1),
    "up-left":    (-1, 0),
}

# Геометрия экрана TH4 (измерена, не взята из исходников):
#   px = anchor_x + (dRow - dCol) * TILE_W/2
#   py = anchor_y + (dRow + dCol) * TILE_H/2
# где (dRow, dCol) — сдвиг клетки относительно героя.
# Важно: герой нарисован НЕ в центре окна, а на ANCHOR_DY пикселей выше
# центра клиентской области (при 2560x1440 это 64 px выше).
TILE_W, TILE_H = 128, 64
ANCHOR_DY = -64


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def wait_fresh(path, max_age=3.0, timeout=10.0):
    """Ждёт свежий снимок (ts не старше max_age секунд)."""
    t_end = time.time() + timeout
    while time.time() < t_end:
        snap = read_json(path)
        if snap and snap.get("player"):
            age = time.time() - float(snap.get("ts") or 0)
            if age <= max_age:
                return snap, age
        time.sleep(0.1)
    return None, None


def client_size(pid):
    """Размер клиентской области окна TH4 (для перевода 0..1 в пиксели)."""
    try:
        import thclick
        hwnd, _ = thclick.find_game_window(pid)
        if not hwnd:
            return None
        return thclick.client_size(hwnd)
    except Exception:
        return None


def dir_to_norm(dir_name, tiles, tw, th, cw, ch):
    """Экранное направление -> нормализованная точка окна (nx, ny).

    Точка считается как ЦЕНТР клетки на расстоянии `tiles` от героя, поэтому
    клик однозначен (на границе между клетками игра выбирает соседа иначе).
    """
    dr, dc = DIRS[dir_name]
    dr, dc = dr * tiles, dc * tiles
    px = 0.5 * cw + (dr - dc) * (tw / 2.0)
    py = 0.5 * ch + ANCHOR_DY + (dr + dc) * (th / 2.0)
    return px / cw, py / ch, dr, dc


def one_shot(args, nx, ny, dr, dc):
    """Один замер: команда -> (dir изменился?) -> (Row/Col изменились?)."""
    snap, age = wait_fresh(args.snap)
    if not snap:
        return None
    p0 = snap["player"]
    print(f"[*] старт: HP {p0.get('CurLife')}/{p0.get('MaxCurLife')} "
          f"({p0.get('Row')},{p0.get('Col')}) dir={p0.get('dir')}")
    if (p0.get("CurLife") or 0) <= 0:
        print("[!] Герой МЁРТВ (CurLife = 0) — ходить не будет. Оживи и повтори.")
        return None

    start_pos = (p0.get("Row"), p0.get("Col"))
    start_dir = p0.get("dir")
    ts = time.time()
    cmd = {"action": "click", "x": round(nx, 4), "y": round(ny, 4),
           "real": not args.post, "seq": 1, "ts": ts}
    atomic_write_json(args.cmd, cmd)

    t_rx = t_dir = t_move = t_last = None
    last_pos, last_dir = start_pos, start_dir
    last_change = time.time()
    frames, last_ts = 0, None
    ack_seen = None
    t_end = time.time() + args.timeout

    while time.time() < t_end:
        snap = read_json(args.snap)
        if snap and snap.get("player"):
            st = float(snap.get("ts") or 0)
            if st != last_ts:
                frames += 1
                last_ts = st
            pos = (snap["player"].get("Row"), snap["player"].get("Col"))
            dr_now = snap["player"].get("dir")
            if dr_now != last_dir:
                last_dir = dr_now
                last_change = time.time()
                if t_dir is None:
                    t_dir = time.time()
            if pos != last_pos:
                last_pos = pos
                last_change = time.time()
                t_last = time.time()
                if t_move is None:
                    t_move = time.time()
            if snap.get("ack") and snap["ack"] != ack_seen:
                ack_seen = snap["ack"]
        if t_move is not None and time.time() - last_change >= args.settle:
            break
        if t_dir is not None and t_move is None and time.time() - last_change >= args.settle:
            break
        time.sleep(0.02)

    return {"start": start_pos, "end": last_pos, "start_dir": start_dir, "end_dir": last_dir,
            "t_rx": (float(snap.get("ack_rx_ts") or 0) or None) if snap else None,
            "rx_latency": ((float(snap.get("ack_rx_ts") or 0) - ts) * 1000)
                          if snap and snap.get("ack_rx_ts") else None,
            "dir_latency": (t_dir - ts) * 1000 if t_dir else None,
            "move_latency": (t_move - ts) * 1000 if t_move else None,
            "walk_ms": (t_last - t_move) * 1000 if (t_last and t_move) else None,
            "moved": last_pos != start_pos,
            "frames": frames,
            "ack": ack_seen}


def stats(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    med = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
    return {"min": vals[0], "med": med, "max": vals[-1], "n": len(vals)}


def main():
    ap = argparse.ArgumentParser(description="Тест обратного канала TH4 (клик -> движение)")
    ap.add_argument("--snap", default=os.path.join(GMOD_DATA_DEFAULT, "snapshot.json"))
    ap.add_argument("--cmd", default=os.path.join(GMOD_DATA_DEFAULT, "bridge_cmd.json"))
    ap.add_argument("--dir", choices=list(DIRS), default="up",
                    help="экранное направление клика относительно центра (герой в центре)")
    ap.add_argument("--tiles", type=float, default=4.0,
                    help="на сколько тайлов кликнуть от центра")
    ap.add_argument("--nx", type=float, default=None, help="явная точка X (0..1)")
    ap.add_argument("--ny", type=float, default=None, help="явная точка Y (0..1)")
    ap.add_argument("--post", action="store_true",
                    help="клик через PostMessage вместо реального курсора")
    ap.add_argument("--timeout", type=float, default=10.0, help="сколько ждать реакции")
    ap.add_argument("--settle", type=float, default=1.0,
                    help="считать героя дошедшим, если позиция не менялась столько секунд")
    ap.add_argument("--repeat", type=int, default=1, help="сколько раз повторить замер")
    args = ap.parse_args()

    snap, age = wait_fresh(args.snap)
    if not snap:
        print(f"[!] Нет свежего снимка ({args.snap}). Запущен ли `d1reader.py watch` "
              f"и находится ли герой в игре?")
        return 2
    p0 = snap["player"]
    print(f"[*] снимок возрастом {age:.2f} с | герой {p0.get('name')} ур.{p0.get('CharLevel')} "
          f"HP {p0.get('CurLife')}/{p0.get('MaxCurLife')} "
          f"| ({p0.get('Row')},{p0.get('Col')}) dir={p0.get('dir')} dlvl={p0.get('dungeon')}")

    if (p0.get("CurLife") or 0) <= 0:
        print("[!] Герой МЁРТВ (CurLife = 0) — он не будет ходить и реагировать на клики. "
              "Оживи его в игре (или начни новую сессию) и повтори тест.")
        return 3

    size = client_size(snap.get("pid"))
    if size and args.nx is None and args.ny is None:
        cw, ch = size
        nx, ny, dr, dc = dir_to_norm(args.dir, args.tiles, TILE_W, TILE_H, cw, ch)
        print(f"[*] цель: экран {args.dir} x{args.tiles:g} тайлов -> "
              f"({cw}x{ch}) px ({nx * cw:.0f},{ny * ch:.0f}) -> norm ({nx:.3f},{ny:.3f})"
              f" | ожидаем сдвиг Row{dr:+.0f} Col{dc:+.0f}")
    else:
        cw = ch = 0
        nx = 0.5 if args.nx is None else args.nx
        ny = 0.5 if args.ny is None else args.ny
        dr = dc = None
        print(f"[*] цель: norm ({nx:.3f},{ny:.3f})")

    results = []
    for i in range(max(1, args.repeat)):
        if i:
            print(f"--- повтор {i + 1}/{args.repeat} ---")
            time.sleep(1.0)
        r = one_shot(args, nx, ny, dr, dc)
        if r is None:
            return 3
        results.append(r)
        print(f"    dir {r['start_dir']}->{r['end_dir']}  "
              f"разворот: {fmt_ms(r['dir_latency'])}  "
              f"движение: {fmt_ms(r['move_latency'])}  "
              f"ходьба: {fmt_ms(r['walk_ms'])}  "
              f"{'СДВИНУЛСЯ' if r['moved'] else 'не сдвинулся (стена?)'}")

    print("=" * 66)
    if len(results) > 1:
        for key, title in (("rx_latency", "подхват команды (reader увидел файл)"),
                           ("dir_latency", "разворот героя (игра увидела клик)"),
                           ("move_latency", "первый сдвиг клетки"),
                           ("walk_ms", "ходьба до конца")):
            s = stats([r[key] for r in results])
            if s:
                print(f"  {title:38s} мин {s['min']:6.0f}  медиана {s['med']:6.0f}  "
                      f"макс {s['max']:6.0f} мс  (n={s['n']})")
    moved = sum(1 for r in results if r["moved"])
    turned = sum(1 for r in results if r["dir_latency"] is not None)
    print(f"  развернулось {turned}/{len(results)}, сдвинулось {moved}/{len(results)}")
    return 0 if moved else 1


def fmt_ms(v):
    return f"{v:6.0f} мс" if v is not None else "   нет"



if __name__ == "__main__":
    sys.exit(main())
