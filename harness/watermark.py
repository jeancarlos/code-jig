import json
import os
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


def strip_watermark(path: str) -> dict:
    result = {"file": path, "zero_width": 0, "directional": 0, "attribution_lines": 0}
    try:
        p = Path(path)
        if not p.is_file():
            return result
        if p.is_symlink() and not str(p.resolve()).startswith(str(Path.cwd())):
            return result
        original = p.read_bytes()
        if is_binary(original):
            return result
        text = original.decode("utf-8")
        had_bom = original.startswith(BOM)
        cleaned = text
        old_cleaned = cleaned
        cleaned = cleaned.replace(_NO_BREAK_SPACE, " ")
        cleaned = cleaned.replace(_NARROW_NO_BREAK_SPACE, " ")
        invisible_chars = "".join(k for k in INVISIBLE_CHARS.keys() if k not in (_NO_BREAK_SPACE, _NARROW_NO_BREAK_SPACE))
        for char in invisible_chars:
            count = cleaned.count(char)
            if count > 0:
                result["zero_width"] += count
            cleaned = cleaned.replace(char, "")
        cleaned = cleaned.replace(_SOFT_HYPHEN, "")
        if old_cleaned != cleaned:
            result["zero_width"] = len(old_cleaned) - len(cleaned.replace(_NO_BREAK_SPACE, " ").replace(_NARROW_NO_BREAK_SPACE, " "))
        old_bytes = cleaned.encode("utf-8")
        cleaned = re.sub(ATTRIBUTION_LINES, b"", old_bytes)
        if old_bytes != cleaned:
            result["attribution_lines"] = (len(old_bytes) - len(cleaned)) // 20
        cleaned = cleaned.decode("utf-8")
        new_bytes = cleaned.encode("utf-8")
        if had_bom and not new_bytes.startswith(BOM):
            new_bytes = BOM + new_bytes
        if original == new_bytes:
            return result
        mode = p.stat().st_mode
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(new_bytes)
        os.replace(str(tmp), str(p))
        p.chmod(mode)
        result["changed"] = True
        return result
    except Exception as e:
        print(f"watermark: error processing {path}: {e}", file=sys.stderr)
        return result


def report_result(result: dict, hook_type: str = "posttooluse") -> None:
    if not result.get("changed"):
        return
    total_changes = result.get("zero_width", 0) + result.get("attribution_lines", 0)
    msg = f"watermark: {result['file']}: stripped {total_changes} watermark items"
    if result.get("zero_width"):
        msg += f" ({result['zero_width']} invisible chars"
        if result.get("attribution_lines"):
            msg += f", {result['attribution_lines']} attribution lines)"
        else:
            msg += ")"
    elif result.get("attribution_lines"):
        msg += f" ({result['attribution_lines']} attribution lines)"
    print(msg, file=sys.stderr)
    if hook_type == "claude-code":
        sys.stdout.write(json.dumps({
            "systemMessage": msg,
            "hookSpecificOutput": {"additionalContext": msg}
        }) + "\n")


def cli(args) -> int:
    for path in (args.path or []):
        result = strip_watermark(path)
        report_result(result, "cli")
    return 0
