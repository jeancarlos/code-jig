# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import re

WORD = re.compile(r"\w+")
RAW_OPEN = re.compile(r'b?r(#*)"')
SAFETY = re.compile(r"^(?:/{2,}|/\*+)[!*\s]*SAFETY\s*:", re.IGNORECASE)
BOUNDARY = {";", "{", "}"}
DECLARATIONS = {"fn", "trait"}


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


def _raw_end(src: str, m: re.Match) -> int:
    end = src.find('"' + m.group(1), m.end())
    return len(src) if end == -1 else end + 1 + len(m.group(1))


def tokens(src: str) -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    i, line = 0, 1
    while i < len(src):
        ch = src[i]
        if ch == "\n":
            line += 1
            i += 1
        elif src.startswith("//", i):
            end = src.find("\n", i)
            end = len(src) if end == -1 else end
            out.append(("comment", src[i:end], line))
            i = end
        elif src.startswith("/*", i):
            end = _skip_block_comment(src, i)
            out.append(("comment", src[i:end], line))
            line += src.count("\n", i, end)
            i = end
        else:
            raw = RAW_OPEN.match(src, i)
            if raw:
                end = _raw_end(src, raw)
            elif ch == '"':
                end = _skip_string(src, i + 1)
            elif ch == "'":
                end = _skip_char(src, i)
            else:
                m = WORD.match(src, i)
                end = m.end() if m else i + 1
                if m:
                    out.append(("word", m.group(), line))
                elif not ch.isspace():
                    out.append(("punct", ch, line))
                i = end
                continue
            out.append(("literal", "", line))
            line += src.count("\n", i, end)
            i = end
    return out


def _is_safety(tok: tuple[str, str, int]) -> bool:
    return tok[0] == "comment" and bool(SAFETY.match(tok[1]))


def _documented(toks: list[tuple[str, str, int]], at: int, opens: int | None) -> bool:
    j = at - 1
    while j >= 0 and not (toks[j][0] == "punct" and toks[j][1] in BOUNDARY):
        if _is_safety(toks[j]):
            return True
        j -= 1
    return opens is not None and opens + 1 < len(toks) and _is_safety(toks[opens + 1])


def _next_code(toks: list[tuple[str, str, int]], i: int) -> int | None:
    i += 1
    while i < len(toks) and toks[i][0] == "comment":
        i += 1
    return i if i < len(toks) else None


def _extern_opens(toks: list[tuple[str, str, int]], i: int) -> int | None:
    while i < len(toks) and toks[i][1] not in ("{", ";", "fn"):
        i += 1
    return i if i < len(toks) and toks[i][1] == "{" else None


def undocumented(src: str) -> tuple[int, list[int]]:
    toks = tokens(src)
    total, bare = 0, []
    for i, (kind, value, line) in enumerate(toks):
        nxt = _next_code(toks, i) if kind == "word" and value == "unsafe" else None
        if nxt is None:
            continue
        follower = toks[nxt][1]
        if follower in DECLARATIONS:
            total += 1
            continue
        opens = {"{": nxt, "extern": _extern_opens(toks, nxt) if follower == "extern" else None}.get(follower)
        if follower in ("{", "impl") or (follower == "extern" and opens is not None):
            total += 1
            if not _documented(toks, i, opens):
                bare.append(line)
        elif follower == "extern":
            total += 1
    return total, bare
