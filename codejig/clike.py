import re

LANGS = {
    ".js": "js", ".mjs": "js", ".jsx": "js", ".ts": "js", ".tsx": "js",
    ".java": "c", ".c": "c", ".cc": "c", ".cpp": "c",
    ".cs": "cs", ".go": "go", ".rs": "rs", ".css": "css",
}
QUOTES = {"js": "\"'`", "c": "\"'", "cs": "\"'", "go": "\"'`", "rs": "\"'", "css": "\"'"}
RUST_CHAR = re.compile(r"'(?:\\[^'\n]*|[^'\\\n])'")


def _quoted(text: str, i: int, multiline: bool) -> int:
    quote, j = text[i], i + 1
    while j < len(text):
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if ch == quote:
            return j + 1
        if ch == "\n" and not multiline:
            return j
        j += 1
    return len(text)


def _after(text: str, i: int, close: str, skip: int = 1) -> int:
    j = text.find(close, i + skip)
    return len(text) if j < 0 else j + len(close)


def _rust_raw(text: str, i: int) -> int | None:
    k = i
    while k > 0 and text[k - 1] == "#":
        k -= 1
    if k == 0 or text[k - 1] != "r":
        return None
    before = text[k - 2] if k > 1 else ""
    if before.isalnum() and before != "b" or before == "_":
        return None
    return _after(text, i, '"' + "#" * (i - k))


def _verbatim(text: str, i: int) -> int:
    j = i + 1
    while True:
        j = text.find('"', j)
        if j < 0:
            return len(text)
        if text[j + 1 : j + 2] != '"':
            return j + 1
        j += 2


def _rust_string(text: str, i: int) -> int:
    if text[i] == '"':
        raw = _rust_raw(text, i)
        return raw if raw is not None else _quoted(text, i, True)
    m = RUST_CHAR.match(text, i)
    return m.end() if m else i + 1


def _string_end(text: str, i: int, lang: str) -> int:
    ch = text[i]
    if lang in ("c", "cs") and text.startswith('"""', i):
        return _after(text, i, '"""', 3)
    if lang == "cs" and ch == '"' and text[i - 1 : i] == "@":
        return _verbatim(text, i)
    if lang == "go" and ch == "`":
        return _after(text, i, "`")
    if lang == "rs":
        return _rust_string(text, i)
    return _quoted(text, i, multiline=lang == "js" and ch == "`")


def _block_end(text: str, i: int, lang: str) -> int:
    if lang != "rs":
        return _after(text, i, "*/", 2)
    depth, j = 1, i + 2
    while j < len(text) and depth:
        two = text[j : j + 2]
        depth += (two == "/*") - (two == "*/")
        j += 2 if two in ("/*", "*/") else 1
    return j


def _tokens(text: str, lang: str):
    i, n = 0, len(text)
    quotes = QUOTES[lang]
    while i < n:
        two = text[i : i + 2]
        if two == "//" and lang != "css":
            end = text.find("\n", i)
            end = n if end < 0 else end
            yield "c", i, end
            i = end
        elif two == "/*":
            end = _block_end(text, i, lang)
            yield "c", i, end
            i = end
        elif text[i] in quotes:
            end = _string_end(text, i, lang)
            yield "s", i, end
            i = end
        else:
            i += 1


def comment_spans(text: str, lang: str) -> list[tuple[int, int]]:
    """(start, end) of every comment, found by walking the file so a comment marker inside
    a string literal is never taken for one."""
    return [(start, end) for kind, start, end in _tokens(text, lang) if kind == "c"]


REGEX_START = re.compile(r"(?:^|[(,=:\[!&|?{};+\-*%<>~^]|\b(?:return|typeof|case|in|of|void|delete|throw))\s*/(?![/*])")


def has_regex_literal(text: str, lang: str) -> bool:
    """True when a `/` in the code could open a regex literal, which this walker does not understand."""
    code, pos = [], 0
    for kind, start, end in _tokens(text, lang):
        code += [text[pos:start], '""' if kind == "s" else " "]
        pos = end
    return bool(REGEX_START.search("".join(code) + text[pos:]))
