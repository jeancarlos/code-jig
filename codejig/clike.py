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


def _string_end(text: str, i: int, lang: str) -> int:
    ch = text[i]
    if lang in ("c", "cs") and text.startswith('"""', i):
        return _after(text, i, '"""', 3)
    if lang == "cs" and ch == '"' and text[i - 1 : i] == "@":
        j = i + 1
        while True:
            j = text.find('"', j)
            if j < 0:
                return len(text)
            if text[j + 1 : j + 2] != '"':
                return j + 1
            j += 2
    if lang == "go" and ch == "`":
        return _after(text, i, "`")
    if lang == "rs":
        if ch == '"':
            raw = _rust_raw(text, i)
            return raw if raw is not None else _quoted(text, i, True)
        m = RUST_CHAR.match(text, i)
        return m.end() if m else i + 1
    return _quoted(text, i, multiline=lang == "js" and ch == "`")


def comment_spans(text: str, lang: str) -> list[tuple[int, int]]:
    """(start, end) of every comment, found by walking the file so a comment marker inside
    a string literal is never taken for one. Regex literals are not understood."""
    spans, i, n = [], 0, len(text)
    quotes = QUOTES[lang]
    while i < n:
        two = text[i : i + 2]
        if two == "//" and lang != "css":
            end = text.find("\n", i)
            end = n if end < 0 else end
            spans.append((i, end))
            i = end
        elif two == "/*":
            end = _after(text, i, "*/", 2)
            spans.append((i, end))
            i = end
        elif text[i] in quotes:
            i = _string_end(text, i, lang)
        else:
            i += 1
    return spans
