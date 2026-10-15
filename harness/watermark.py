import re
import sys
from pathlib import Path

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
    rb"generated with[^\n]*(?:claude[^\n]*|codex[^\n]*|chatgpt[^\n]*)|"
    rb"[^\n]*\xf0\x9f\xa4\x96 generated[^\n]*|"
    rb"(?:ai-assisted|ai-generated)[^\n]*"
    rb")[ \t]*\n?"
)

BOM = b"\xef\xbb\xbf"
_NO_BREAK_SPACE = chr(0x00a0)
_NARROW_NO_BREAK_SPACE = chr(0x202f)
_SOFT_HYPHEN = chr(0x00ad)


def is_binary(data: bytes) -> bool:
    try:
        data.decode("utf-8", errors="strict")
        return False
    except UnicodeDecodeError:
        return True


def strip_watermark(path: str) -> bool:
    try:
        p = Path(path)
        if not p.is_file():
            return True
        original = p.read_bytes()
        if is_binary(original):
            return True
        text = original.decode("utf-8")
        had_bom = original.startswith(BOM)
        cleaned = text
        cleaned = cleaned.replace(_NO_BREAK_SPACE, " ")
        cleaned = cleaned.replace(_NARROW_NO_BREAK_SPACE, " ")
        invisible_chars = "".join(k for k in INVISIBLE_CHARS.keys() if k not in (_NO_BREAK_SPACE, _NARROW_NO_BREAK_SPACE))
        cleaned = re.sub(f"[{re.escape(invisible_chars)}]", "", cleaned)
        cleaned = cleaned.replace(_SOFT_HYPHEN, "")
        cleaned = re.sub(ATTRIBUTION_LINES, b"", cleaned.encode("utf-8")).decode("utf-8")
        new_bytes = cleaned.encode("utf-8")
        if had_bom and not new_bytes.startswith(BOM):
            new_bytes = BOM + new_bytes
        if original == new_bytes:
            return True
        p.write_bytes(new_bytes)
        return True
    except Exception as e:
        print(f"watermark: error processing {path}: {e}", file=sys.stderr)
        return True


def cli(args) -> int:
    for path in (args.path or []):
        strip_watermark(path)
    return 0
