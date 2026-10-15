import re
import sys

from harness.atomicwrite import atomic_write, resolve_inside

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

ATTRIBUTION_LINES = re.compile(
    rb"(?mi)^[ \t]*("
    rb"co-authored-by:[^\n]*(?:claude|codex|chatgpt|an ai)[^\n]*|"
    rb"claude-session:[^\n]*|"
    rb"generated with[^\n]*(?:claude[^\n]*|codex[^\n]*|chatgpt[^\n]*)|"
    rb"[^\n]*\xf0\x9f\xa4\x96 generated[^\n]*|"
    rb"(?:ai-assisted|ai-generated)[^\n]*"
    rb")[ \t]*\n?"
)

BOM = b"\xef\xbb\xbf"
_NO_BREAK_SPACE = chr(0x00a0)
_NARROW_NO_BREAK_SPACE = chr(0x202f)
_SOFT_HYPHEN = chr(0x00ad)
_BIDI = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}


def is_binary(data: bytes) -> bool:
    try:
        data.decode("utf-8", errors="strict")
        return False
    except UnicodeDecodeError:
        return True


def strip_bytes(original: bytes, attribution: bool = True) -> tuple[bytes, dict]:
    """Watermark-free bytes and how many of each kind were removed."""
    counts = {"zero_width": 0, "directional": 0, "attribution_lines": 0}
    text = original.decode("utf-8")
    had_bom = text.startswith("\ufeff")
    if had_bom:
        text = text[1:]
    out = []
    for ch in text:
        if ch in (_NO_BREAK_SPACE, _NARROW_NO_BREAK_SPACE):
            out.append(" ")
            counts["zero_width"] += 1
        elif ch in INVISIBLE_CHARS:
            counts["directional" if ch in _BIDI else "zero_width"] += 1
        else:
            out.append(ch)
    data = "".join(out).encode("utf-8")
    if attribution:
        counts["attribution_lines"] = len(ATTRIBUTION_LINES.findall(data))
        data = ATTRIBUTION_LINES.sub(b"", data)
    return (BOM + data if had_bom else data), counts


def strip_watermark(path: str, root: str | None = None) -> dict:
    result = {"file": path, "zero_width": 0, "directional": 0, "attribution_lines": 0}
    target = resolve_inside(path, root)
    if target is None:
        return result
    try:
        original = target.read_bytes()
        if is_binary(original):
            return result
        cleaned, counts = strip_bytes(original)
        result.update(counts)
        if cleaned != original:
            atomic_write(target, cleaned)
            result["changed"] = True
    except Exception as e:
        print(f"watermark: error processing {path}: {e}", file=sys.stderr)
    return result


def report_result(result: dict, hook_type: str = "cli") -> str | None:
    if not result.get("changed"):
        return None
    parts = [
        f"{result[k]} {label}"
        for k, label in (
            ("zero_width", "invisible chars"),
            ("directional", "bidi controls"),
            ("attribution_lines", "attribution lines"),
        )
        if result.get(k)
    ]
    msg = f"watermark: {result['file']}: stripped {', '.join(parts)}"
    print(msg, file=sys.stderr)
    return msg


def cli(args) -> int:
    for path in (args.path or []):
        result = strip_watermark(path)
        report_result(result, "cli")
    return 0
