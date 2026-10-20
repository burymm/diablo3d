#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
luacheck.py — грубая проверка Lua-файла без интерпретатора Lua.

Что ловит:
  * несбалансированные блоки (function/if/for/while/repeat против end/until);
  * строку, где комментарий «съел» код: `-- текст concommand.Add(...)` —
    именно так в аддоне один раз потерялась целая команда и GMod падал при
    загрузке карты;
  * concommand.Add без function сразу после скобки;
  * BOM/LF-переводы строк (GMod терпим, но лучше знать).

Это не парсер: он не поймает ошибку в выражении. Но полезную часть ловит.

    python luacheck.py <файл.lua>
"""
import os
import re
import sys


def strip_comments_and_strings(src):
    src = re.sub(r"--\[\[.*?\]\]", " ", src, flags=re.S)
    src = re.sub(r"--[^\n]*", " ", src)
    src = re.sub(r'"(\\.|[^"\\])*"', '""', src)
    src = re.sub(r"'(\\.|[^'\\])*'", "''", src)
    return src


SPEC_RE = re.compile(r"%[-+ #0-9.]*[sdifq]")


def _call_args(call):
    """Аргументы вызова по запятым верхнего уровня (строковые литералы не режем)."""
    args, cur, depth, i, n = [], [], 0, 0, len(call)
    quote = None
    while i < n:
        ch = call[i]
        if quote:
            if ch == "\\":
                cur.append(ch)
                if i + 1 < n:
                    cur.append(call[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            cur.append(ch)
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in "({[":
            depth += 1
            cur.append(ch)
        elif ch in ")}]":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if "".join(cur).strip():
        args.append("".join(cur))
    return args


def check_format(path):
    """string.format: столько же плейсхолдеров, сколько аргументов.

    Ловит класс ошибок вида "bad argument #N to 'format'" — самый частый в
    этом аддоне после правок: удалили поле, а ссылка на него осталась.
    """
    src = open(path, encoding="utf-8").read()
    bad = 0
    for m in re.finditer(r"string\.format\(", src):
        depth, i, start = 1, m.end(), m.end()
        quote = None
        while i < len(src) and depth > 0:
            ch = src[i]
            if quote:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch in "({[":
                depth += 1
            elif ch in ")}]":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        args = _split = _call_args(src[start:i])
        if len(args) < 2:
            continue
        pattern = args[0]
        # убираем экранированные проценты, считаем спецификаторы
        specs = len(SPEC_RE.findall(pattern.replace("%%", "")))
        n_args = len(args) - 1
        if specs != n_args:
            line = src[:m.start()].count("\n") + 1
            print(f"  ! строка {line}: string.format — плейсхолдеров {specs}, "
                  f"аргументов {n_args} | {pattern.strip()[:40]}")
            bad += 1
    return bad


def check(path):
    raw = open(path, "rb").read()
    problems = []
    print(f"файл: {path}")
    print(f"  BOM: {raw[:3] == b'\xef\xbb\xbf'} | CRLF: {raw.count(b'\r\n')} | "
          f"строк: {raw.count(b'\n') + 1} | байт: {len(raw)}")
    if raw[:3] == b"\xef\xbb\xbf":
        problems.append("файл начинается с BOM — GMod обычно терпит, но лучше без него")

    src = raw.decode("utf-8", "replace")
    lines = src.splitlines()

    # 1. комментарий, после которого идёт код
    for i, ln in enumerate(lines, 1):
        m = re.search(r"--", ln)
        if m and re.search(r"\b(concommand\.Add|hook\.Add|timer\.Create|local|print|end)\b",
                           ln[m.end():]):
            problems.append(f"строка {i}: код внутри комментария -> {ln.strip()[:80]}")

    # 2. баланс блоков
    clean = strip_comments_and_strings(src)
    opens = len(re.findall(r"\b(function|if|for|while|repeat)\b", clean))
    # Отдельные блоки `do ... end` (не `for ... do` / `while ... do`) тоже
    # открывают блок — иначе баланс считается неверно.
    opens += len(re.findall(r"(?m)^\s*do\b(?![^\n]*\b(for|while)\b)", clean))
    closes = len(re.findall(r"\bend\b|\buntil\b", clean))
    balance = opens - closes
    print(f"  блоков открыто {opens}, закрыто {closes}, баланс {balance}")
    if balance:
        problems.append(f"баланс блоков {balance} — синтаксическая ошибка (пропущен/лишний end)")

    # 3. concommand.Add без function
    for i, ln in enumerate(lines, 1):
        if "concommand.Add(" in ln and "function" not in ln:
            problems.append(f"строка {i}: concommand.Add без function -> {ln.strip()[:80]}")

    n_fmt = check_format(path)
    if n_fmt:
        problems.append(f"несогласованных string.format: {n_fmt}")

    if problems:
        print("\nПРОБЛЕМЫ:")
        for p in problems:
            print(f"  ! {p}")
        return 1
    print("\nгрубых проблем не найдено")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        here = os.path.dirname(os.path.abspath(__file__))
        args = [os.path.join(here, os.pardir, "gmod", "d1bridge.lua")]
    rc = 0
    for a in args:
        rc |= check(a)
        print()
    sys.exit(rc)
