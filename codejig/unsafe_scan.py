# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import re

WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
RAW_OPEN = re.compile(r'b?r(#*)"')
WINDOW_BEFORE, WINDOW_AFTER = 3, 1


def _skip_string(src: str, i: int) -> int:
    while i < len(src) and src[i] != '"':
        i += 2 if src[i] == "\\" else 1
    return i + 1


def _skip_char(src: str, i: int) -> int:
    if src[i + 1:i + 2] == "\\":
        end = src.find("'", i + 2)
        return end + 1 if end != -1 else i + 1
    return i + 3 if src[i + 2:i + 3] == "'" else i + 1


def _skip_block_comment(src: str, i: int) -> int:
    depth = 0
    while i < len(src):
        pair = src[i:i + 2]
        if pair == "/*":
            depth, i = depth + 1, i + 2
        elif pair == "*/":
            depth, i = depth - 1, i + 2
            if depth == 0:
                return i
        else:
            i += 1
    return i


def scan(src: str) -> tuple[list[int], list[tuple[int, int]]]:
    unsafe_lines: list[int] = []
    safety: list[tuple[int, int]] = []
    i, line = 0, 1
    while i < len(src):
        ch = src[i]
        if ch == "\n":
            line += 1
            i += 1
        elif src.startswith("//", i):
            end = src.find("\n", i)
            end = len(src) if end == -1 else end
            if "safety" in src[i:end].lower():
                safety.append((line, line))
            i = end
        elif src.startswith("/*", i):
            end = _skip_block_comment(src, i)
            body = src[i:end]
            if "safety" in body.lower():
                safety.append((line, line + body.count("\n")))
            line += body.count("\n")
            i = end
        elif RAW_OPEN.match(src, i):
            m = RAW_OPEN.match(src, i)
            end = src.find('"' + m.group(1), m.end())
            end = len(src) if end == -1 else end + 1 + len(m.group(1))
            line += src.count("\n", i, end)
            i = end
        elif ch == '"':
            end = _skip_string(src, i + 1)
            line += src.count("\n", i, end)
            i = end
        elif ch == "'":
            i = _skip_char(src, i)
        elif ch.isalpha() or ch == "_":
            m = WORD.match(src, i)
            if m.group() == "unsafe" and re.match(r"\s*(\{|impl\b|extern\b)", src[m.end():m.end() + 40]):
                unsafe_lines.append(line)
            i = m.end()
        else:
            i += 1
    return unsafe_lines, safety


def undocumented(src: str) -> tuple[int, list[int]]:
    lines, safety = scan(src)
    bare = [n for n in lines if not any(start <= n + WINDOW_AFTER and end >= n - WINDOW_BEFORE for start, end in safety)]
    return len(lines), bare
