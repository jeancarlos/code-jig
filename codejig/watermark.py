# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import io
import re
import sys
import tokenize

from codejig.atomicwrite import atomic_write, resolve_inside

_CHAR_CODES = [
    (0x200b, "ZERO WIDTH SPACE"),
    (0x200c, "ZERO WIDTH NON-JOINER"),
    (0x200d, "ZERO WIDTH JOINER"),
    (0x2060, "WORD JOINER"),
    (0x2061, "FUNCTION APPLICATION"),
    (0x2062, "INVISIBLE TIMES"),
    (0x2063, "INVISIBLE SEPARATOR"),
    (0x2064, "INVISIBLE PLUS"),
    (0x180e, "MONGOLIAN VOWEL SEPARATOR"),
    (0xfeff, "ZERO WIDTH NO-BREAK SPACE"),
    (0x00ad, "SOFT HYPHEN"),
    (0x202f, "NARROW NO-BREAK SPACE"),
    (0x00a0, "NO-BREAK SPACE"),
    (0x202a, "LEFT-TO-RIGHT EMBEDDING"),
    (0x202b, "RIGHT-TO-LEFT EMBEDDING"),
    (0x202c, "POP DIRECTIONAL FORMATTING"),
    (0x202d, "LEFT-TO-RIGHT OVERRIDE"),
    (0x202e, "RIGHT-TO-LEFT OVERRIDE"),
    (0x2066, "LEFT-TO-RIGHT ISOLATE"),
    (0x2067, "RIGHT-TO-LEFT ISOLATE"),
    (0x2068, "FIRST STRONG ISOLATE"),
    (0x2069, "POP DIRECTIONAL ISOLATE"),
]
INVISIBLE_CHARS = {chr(code): name for code, name in _CHAR_CODES}

_TOOLS = rb"claude|codex|chatgpt|gpt-?\d+|github[ \t]+copilot|copilot|gemini|antigravity|cursor|aider|devin|jules|openai|anthropic"
_PRODUCT_WORDS = rb"code|agent|ai|assistant|cli|opus|sonnet|haiku|fable|pro|flash|ultra|\d+(?:\.\d+)*"
_TOOL_NAME = rb"(?:claude|codex|chatgpt|gpt-?\d+|github[ \t]+copilot|copilot|gemini|antigravity|cursor[ \t]+agent|aider|devin[ \t]+ai|jules)(?:[ \t]+(?:" + _PRODUCT_WORDS + rb"))*"
_TOOL_DOMAINS = rb"anthropic\.com|openai\.com|cursor\.com|cognition\.ai|cognition-labs\.com|aider\.chat"
_AI_BOT = rb"[\w.-]*(?:" + _TOOLS + rb")[\w.-]*\[bot\]"
ATTRIBUTION = re.compile(
    rb"(?i)[ \t]*(?:"
    rb"co-authored-by:(?:[ \t]*" + _TOOL_NAME + rb"[ \t]*(?:<[^>\n]*>)?|"
    rb"[ \t]*" + _AI_BOT + rb"[^\n]*|"
    rb"[^\n]*<[^>\n]*@(?:" + _TOOL_DOMAINS + rb")>[^\n]*|"
    rb"[^\n]*\ban ai\b[^\n]*)|"
    rb"claude-session:[^\n]*|"
    rb"generated (?:with|by)[ \t]+\[?(?:" + _TOOLS + rb")\b[^\n]*|"
    rb"made with cursor[^\n]*|"
    rb"[^\n]*\xf0\x9f\xa4\x96 generated[^\n]*|"
    rb"ai-(?:assisted|generated)(?:[ \t]*:[^\n]*)?"
    rb")[ \t]*\r?"
)
TRAILER = re.compile(rb"[ \t]*[A-Za-z0-9-]+:[ \t]")
SCISSORS = re.compile(rb"#[ \t]*-+ >8 -+[ \t]*\r?\n?")
TEXT = re.compile(r"(?i)\.(?:md|mdx|markdown|rst|adoc|txt)$")
_STRING_STARTS = {getattr(tokenize, n) for n in ("FSTRING_START", "TSTRING_START") if hasattr(tokenize, n)}
_STRING_ENDS = {getattr(tokenize, n) for n in ("FSTRING_END", "TSTRING_END") if hasattr(tokenize, n)}

BOM = b"\xef\xbb\xbf"
_NO_BREAK_SPACE = chr(0x00a0)
_NARROW_NO_BREAK_SPACE = chr(0x202f)
_SOFT_HYPHEN = chr(0x00ad)
_BIDI = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
_JOINERS = {chr(0x200C), chr(0x200D)}


def is_binary(data: bytes) -> bool:
    try:
        data.decode("utf-8", errors="strict")
        return False
    except UnicodeDecodeError:
        return True


def _joins(text: str, i: int) -> bool:
    a, b = text[i - 1:i] if i else "", text[i + 1:i + 2]
    return all(c and not c.isascii() and not c.isspace() and c not in INVISIBLE_CHARS for c in (a, b))


def _strip_chars(text: str, locked=None) -> tuple[str, dict, list[int]]:
    counts = {"zero_width": 0, "directional": 0}
    out, left = [], []
    for i, ch in enumerate(text):
        if ch not in INVISIBLE_CHARS or (ch in _JOINERS and _joins(text, i)):
            out.append(ch)
        elif locked and locked(i):
            out.append(ch)
            left.append(i)
        elif ch in (_NO_BREAK_SPACE, _NARROW_NO_BREAK_SPACE):
            out.append(" ")
            counts["zero_width"] += 1
        else:
            counts["directional" if ch in _BIDI else "zero_width"] += 1
    return "".join(out), counts, left


def _python_strings(text: str) -> list[tuple[int, int]] | None:
    """Character spans of the string literals in Python source, or None if it does not tokenize."""
    masked = "".join(" " if c in INVISIBLE_CHARS else c for c in text)
    starts = [0]
    for line in masked.split("\n"):
        starts.append(starts[-1] + len(line) + 1)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(masked).readline))
    except (tokenize.TokenError, SyntaxError):
        return None
    spans, depth, begin = [], 0, 0
    for t in tokens:
        at = starts[t.start[0] - 1] + t.start[1]
        if t.type == tokenize.STRING and not depth:
            spans.append((at, starts[t.end[0] - 1] + t.end[1]))
        elif t.type in _STRING_STARTS:
            begin = at if not depth else begin
            depth += 1
        elif t.type in _STRING_ENDS:
            depth -= 1
            if not depth:
                spans.append((begin, starts[t.end[0] - 1] + t.end[1]))
    return spans


def _locked(text: str, path: str):
    if TEXT.search(path):
        return None
    spans = _python_strings(text) if path.lower().endswith(".py") else None
    if spans is None:
        return lambda i: True
    return lambda i: any(start <= i < end for start, end in spans)


def strip_file(original: bytes, path: str) -> tuple[bytes, dict]:
    """The file with the invisible characters removed that cannot be meant there, and a report.

    Prose files lose them anywhere; Python loses them outside string literals; nothing else
    is edited. `left` lists the lines whose characters were kept because they may be meant,
    `attribution` the lines that look like AI attribution, which files never lose."""
    text = original.decode("utf-8")
    had_bom = text.startswith("\ufeff")
    if had_bom:
        text = text[1:]
    cleaned, counts, left = _strip_chars(text, _locked(text, path))
    counts["left"] = sorted({text.count("\n", 0, i) + 1 for i in left})
    counts["attribution"] = [n for n, line in enumerate(cleaned.encode("utf-8").split(b"\n"), 1) if ATTRIBUTION.fullmatch(line)]
    data = cleaned.encode("utf-8")
    return (BOM + data if had_bom else data), counts


def _drop_attribution(data: bytes) -> bytes:
    """`data` without the attribution lines of its closing trailer paragraphs; the subject is never touched."""
    lines = data.splitlines(keepends=True)
    end = next((n for n, line in enumerate(lines) if SCISSORS.fullmatch(line)), len(lines))
    drop, k = set(), end
    while k > 1:
        while k > 1 and (not lines[k - 1].strip() or lines[k - 1].startswith(b"#")):
            k -= 1
        para = []
        while k > 1 and lines[k - 1].strip():
            if not lines[k - 1].startswith(b"#"):
                para.append(k - 1)
            k -= 1
        hits = {n for n in para if ATTRIBUTION.fullmatch(lines[n].rstrip(b"\n"))}
        if any(n not in hits and not TRAILER.match(lines[n]) for n in para):
            break
        drop |= hits
    return b"".join(line for n, line in enumerate(lines) if n not in drop)


def clean_message(msg: bytes) -> bytes:
    try:
        data = _strip_chars(msg.decode("utf-8"))[0].encode("utf-8")
    except UnicodeDecodeError:
        data = msg
    new = _drop_attribution(data)
    return msg if new == msg else new.rstrip(b"\n") + b"\n"


def has_watermark(msg: bytes) -> bool:
    return clean_message(msg) != msg


def strip_watermark(path: str, root: str | None = None) -> dict:
    result = {"file": path, "zero_width": 0, "directional": 0, "left": [], "attribution": []}
    target = resolve_inside(path, root)
    if target is None:
        return result
    try:
        original = target.read_bytes()
        if is_binary(original):
            return result
        cleaned, counts = strip_file(original, path)
        result.update(counts)
        if cleaned != original:
            atomic_write(target, cleaned)
            result["changed"] = True
    except Exception as e:
        print(f"watermark: error processing {path}: {e}", file=sys.stderr)
    return result


def _lines(numbers: list[int]) -> str:
    return f"line{'s' if len(numbers) > 1 else ''} {', '.join(map(str, numbers))}"


def report_result(result: dict) -> str | None:
    parts = [f"{result[k]} {label}" for k, label in (("zero_width", "invisible chars"), ("directional", "bidi controls"))
             if result.get("changed") and result.get(k)]
    notes = [f"stripped {', '.join(parts)}"] if parts else []
    if result.get("left"):
        notes.append(f"{_lines(result['left'])} keep invisible characters that may be meant in code or data; "
                     "write them as escapes or delete them")
    if result.get("attribution"):
        notes.append(f"{_lines(result['attribution'])} looks like AI attribution, not removed: delete it unless it is meant")
    if not notes:
        return None
    msg = f"watermark: {result['file']}: {'; '.join(notes)}"
    print(msg, file=sys.stderr)
    return msg


def cli(args) -> int:
    for path in (args.path or []):
        result = strip_watermark(path)
        report_result(result)
    return 0
