#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
thclick.py — синтетический клик в окно TH4 (обратный канал, этап 1).

Идея (Р-8 «клик-фолбэк»): GMod пишет команду в файл, reader её читает и
кликает в окно игры. Игра сама решает, что делать (движение/атака) — мы
не пишем в её память, только эмулируем ввод мыши.

Почему реальный ввод (SetCursorPos + mouse_event), а не PostMessage:
TH4 — старая игра (Hellfire), ввод читает через DirectInput/поллинг курсора,
поэтому сообщения окну она может игнорировать.

Безопасность: клик уходит по АБСОЛЮТНЫМ координатам экрана. Если окно TH4
не на переднем плане, клик попадёт в другое приложение. Поэтому перед кликом
окно поднимается и проверяется (GetForegroundWindow); если не получилось —
клик не делаем.
"""
import ctypes
import os
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

SW_RESTORE = 9

# Пауза между перемещением курсора и кликом: TH4 читает позицию курсора
# раз в кадр, без паузы клик может уйти в старую точку.
MOVE_DELAY = 0.05
# Доставка ввода на фоне: игра обновляет свой курсор по кадрам, поэтому шлём
# СЕРИЮ WM_MOUSEMOVE с паузами и только потом клик. Одного сообщения мало:
# клик обрабатывался по ПРЕДЫДУЩЕЙ позиции (сдвиг ровно на одну команду).
MOUSE_MOVES = 2
MOUSE_MOVE_GAP = 0.03
# Сколько курсор остаётся в точке клика после нажатия (игра успевает прочитать).
# Чем меньше, тем короче «дёрганье» курсора у пользователя.
CLICK_DWELL = 0.08
# Быстрый режим: курсор смещается всего на ~60 мс. Меньше «дёрганья» для
# пользователя, но если игра не успевает прочитать позицию — клик может
# пропасть (тогда удержание повторит, а одиночный шаг придётся повторить руками).
QUICK_MOVES = 1
QUICK_GAP = 0.02
QUICK_DWELL = 0.04
# Пауза перед нажатием в режиме настоящей кнопки.
POST_MOVE_DELAY = float(os.environ.get("D1_POST_DELAY", "0.15"))
# Пауза между нажатием и отпусканием кнопки.
BUTTON_DELAY = 0.02

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint), ("flags", ctypes.c_uint),
                ("showCmd", ctypes.c_uint), ("ptMinPosition", POINT),
                ("ptMaxPosition", POINT), ("rcNormalPosition", RECT)]


# Последний известный непустой размер клиентской области (на случай,
# если окно свернуто и GetClientRect отдаёт 0x0).
_LAST_CLIENT_SIZE = {"size": (0, 0)}


_enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

# --- прототипы: на x64 HWND — указатель, ctypes по умолчанию режет его до int ---
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                            ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                               wintypes.DWORD, ctypes.c_size_t]
user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_long]
user32.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.GetWindowPlacement.restype = wintypes.BOOL
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.AdjustWindowRectEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                      wintypes.BOOL, ctypes.c_ulong]
user32.AdjustWindowRectEx.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

GWL_STYLE = -16
GWL_EXSTYLE = -20


def _find_windows_for_pid(pid):
    found = []

    def cb(hwnd, _):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(_enum_proc(cb), 0)
    return found


def find_game_window(pid):
    """Возвращает hwnd окна игры с самой большой клиентской областью."""
    best, best_area = None, -1
    for hwnd in _find_windows_for_pid(pid):
        r = RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(r)):
            continue
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > best_area:
            best, best_area = hwnd, area
    return best, best_area


def client_size(hwnd):
    """Размер клиентской области окна.

    У СВЁРНУТОГО окна GetClientRect отдаёт 0x0, хотя окно продолжает жить
    и принимать PostMessage. Порядок:
      1. GetClientRect — если непустой, запоминаем и возвращаем;
      2. кэш последнего непустого размера (окно свернули после успеха);
      3. GetWindowPlacement(rcNormalPosition) минус рамка, посчитанная
         через AdjustWindowRectEx по стилю окна (окно свернуто сразу).
    """
    r = RECT()
    if user32.GetClientRect(hwnd, ctypes.byref(r)):
        w, h = r.right - r.left, r.bottom - r.top
        if w > 0 and h > 0:
            _LAST_CLIENT_SIZE["size"] = (w, h)
            return (w, h)

    cached = _LAST_CLIENT_SIZE["size"]
    if cached[0] > 0 and cached[1] > 0:
        return cached

    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(WINDOWPLACEMENT)
    if user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        nr = wp.rcNormalPosition
        w, h = nr.right - nr.left, nr.bottom - nr.top
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        box = RECT(0, 0, w, h)
        user32.AdjustWindowRectEx(ctypes.byref(box), ctypes.c_ulong(style),
                                   False, ctypes.c_ulong(exstyle))
        cw, ch = box.right - box.left, box.bottom - box.top
        if cw > 0 and ch > 0:
            _LAST_CLIENT_SIZE["size"] = (cw, ch)
            return (cw, ch)

    return cached


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def foreground_hwnd():
    return user32.GetForegroundWindow()


def window_pid(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def is_foreground(hwnd):
    return foreground_hwnd() == hwnd


def activate_window(hwnd):
    """Поднимает окно и проверяет, что оно стало активным.

    Windows не даёт SetForegroundWindow сработать «просто так»: если
    foreground принадлежит другому потоку, нужен AttachThreadInput.
    Возвращает (ok, описание).
    """
    if is_foreground(hwnd):
        return True, "уже на переднем плане"

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.05)

    cur_tid = kernel32.GetCurrentThreadId()
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)

    attached = []
    for tid in {fg_tid, tgt_tid}:
        if tid and tid != cur_tid:
            if user32.AttachThreadInput(cur_tid, tid, True):
                attached.append(tid)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        for tid in attached:
            user32.AttachThreadInput(cur_tid, tid, False)

    time.sleep(0.05)          # окну нужно время на активацию
    if is_foreground(hwnd):
        return True, "окно активировано"

    fg = user32.GetForegroundWindow()
    fg_pid = window_pid(fg) if fg else 0
    return False, (f"окно не стало активным (на переднем плане pid={fg_pid}, "
                   f"\"{window_title(fg) if fg else '?'}\")")


def client_origin(hwnd):
    """Левый верхний угол КЛИЕНТСКОЙ области на экране (в «нормальном» положении).

    Считается от rcNormalPosition (GetWindowPlacement) минус рамка окна, поэтому
    работает и для свёрнутого окна: у свёрнутого окна текущие экранные
    координаты бессмысленны, а «нормальное» положение — как раз то, где игра
    (DirectInput / GetCursorPos) видит свою клиентскую область.
    """
    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(WINDOWPLACEMENT)
    if not user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        return 0, 0
    nr = wp.rcNormalPosition
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    box = RECT(0, 0, nr.right - nr.left, nr.bottom - nr.top)
    user32.AdjustWindowRectEx(ctypes.byref(box), ctypes.c_ulong(style),
                               False, ctypes.c_ulong(exstyle))
    return nr.left + box.left, nr.top + box.top


def get_cursor():
    p = POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def _post_click(hwnd, x, y):
    lp = (y << 16) | (x & 0xFFFF)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


def click_norm(hwnd, nx=0.5, ny=0.5, real=False, require_fg=True, quick=False):
    """Клик в точку (nx, ny) в нормализованных координатах клиентской области.

    **Что выяснено экспериментально (16.10.2026):**
    1. TH4 берёт позицию клика из НАСТОЯЩЕГО системного курсора. Один
       PostMessage с lParam без движения курсора бесполезен: герой идёт туда,
       где курсор реально лежит (проверено: курсор в (300,1000) -> герой шёл
       в ту сторону, а не куда просили).
    2. Одного WM_MOUSEMOVE перед кликом мало: игра обновляет свой курсор по
       кадрам. Нужна СЕРИЯ сообщений, разнесённых по времени. Одиночный клик
       давал сдвиг ровно «на одну команду назад» — игра обрабатывала клик по
       предыдущей позиции.
    3. **Окно TH4 должно быть РАЗВЁРНУТЫМ.** Свёрнутое окно не работает:
       игра не обрабатывает ввод, пока окно свёрнуто. При этом окно может
       быть НЕ В ФОКУСЕ (перекрыто GMod, фокус у GMod) — это проверено 8 из 8.

    real=False (по умолчанию) -> «курсор + серия WM_MOUSEMOVE + PostMessage»:
        окно не поднимаем, фокус не забираем, курсор пользователю возвращаем.
    real=True               -> то же, но с поднятием окна и настоящим нажатием
        (нужно, если окно должно быть видно; забирает фокус).
    """
    w, h = client_size(hwnd)
    if w <= 0 or h <= 0:
        return False, ("неизвестен размер окна (свернуто и нет кэша); "
                       "разверни TH4 один раз")
    if user32.IsIconic(hwnd) and not real:
        return False, ("окно TH4 свёрнуто — игра ввод не обрабатывает "
                       "(проверено 16.10.2026); разверни окно, оставить можно "
                       "на втором мониторе или под GMod")
    x = max(0, min(w - 1, int(nx * w)))
    y = max(0, min(h - 1, int(ny * h)))

    ox, oy = client_origin(hwnd)
    target = (ox + x, oy + y)
    saved = get_cursor()

    if not real:
        moves = QUICK_MOVES if quick else MOUSE_MOVES
        gap = QUICK_GAP if quick else MOUSE_MOVE_GAP
        dwell = QUICK_DWELL if quick else CLICK_DWELL
        user32.SetCursorPos(*target)
        lp = (y << 16) | (x & 0xFFFF)
        # серия WM_MOUSEMOVE, разнесённая по кадрам: игра обновляет свой курсор
        # не сразу, а по кадрам (одного сообщения не хватает)
        for _ in range(moves):
            user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
            time.sleep(gap)
        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)
        time.sleep(dwell)            # курсор пока в нужной точке — даём
                                     # игре обработать нажатие
        user32.SetCursorPos(*saved)  # вернуть курсор пользователю
        return True, (f"PostMessage+курсор{' [быстро]' if quick else ''} at {x},{y} screen {target} "
                      f"(client {w}x{h}, окно {'в фокусе' if is_foreground(hwnd) else 'НЕ в фокусе'})")

    ok, info = activate_window(hwnd)
    if not ok:
        if require_fg:
            return False, f"клик отменён: {info}"
        _post_click(hwnd, x, y)
        return True, f"{info}; fallback PostMessage at {x},{y}"

    ox, oy = client_origin(hwnd)
    target = (ox + x, oy + y)
    user32.SetCursorPos(*target)
    cur = get_cursor()
    if cur != target:
        return False, f"курсор не переместился {cur} != {target}"

    time.sleep(POST_MOVE_DELAY)     # игра читает курсор раз в кадр
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(BUTTON_DELAY)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return True, f"click at {x},{y} screen {target} (client {w}x{h})"


if __name__ == "__main__":
    import sys
    import argparse

    ap = argparse.ArgumentParser(description="Проверка клика в окно TH4")
    ap.add_argument("pid", nargs="?", type=int, default=0,
                    help="pid процесса TH4 (0 — найти единственный TH4.exe)")
    ap.add_argument("--x", type=float, default=0.5)
    ap.add_argument("--y", type=float, default=0.5)
    ap.add_argument("--post", action="store_true", help="через PostMessage")
    ap.add_argument("--info", action="store_true", help="только показать окно")
    a = ap.parse_args()

    pid = a.pid
    if not pid:
        import subprocess
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            from d1reader import TH4_EXE
        except ImportError:
            TH4_EXE = "th43d.exe"
        try:
            out = subprocess.check_output(["tasklist", "/FI", f"IMAGENAME eq {TH4_EXE}"],
                                          text=True, errors="ignore")
        except Exception:
            out = ""
        for line in out.splitlines():
            if TH4_EXE.lower() in line.lower():
                parts = line.split()
                if len(parts) > 1 and parts[1].isdigit():
                    pid = int(parts[1])
                    break
    if not pid:
        print(f"{TH4_EXE} не найден")
        sys.exit(1)

    hwnd, area = find_game_window(pid)
    print(f"pid={pid} hwnd={hwnd} client={client_size(hwnd) if hwnd else None} "
          f"title={window_title(hwnd) if hwnd else None}")
    print(f"foreground={foreground_hwnd()} "
          f"{'СОВПАДАЕТ' if hwnd and is_foreground(hwnd) else 'другое окно'}")
    if a.info or not hwnd:
        sys.exit(0 if hwnd else 2)

    ok, info = click_norm(hwnd, a.x, a.y, real=not a.post)
    print(("OK   " if ok else "FAIL ") + info)
    sys.exit(0 if ok else 3)
