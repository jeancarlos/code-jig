import os
import re
import sys
from pathlib import Path

DASHES = str.maketrans({"—": "-", "–": "-", "―": "-"})
CURLY_QUOTES = str.maketrans({
    "‘": "'", "’": "'",
    "“": '"', "”": '"',
})
ELLIPSIS = "…"

LLM_BOILERPLATE = [
    "Certainly",
    "Here's the updated",
    "Here is the updated",
    "I hope this helps",
    "Let me know if",
    "Feel free to",
    "As an AI",
    "As an assistant",
    "Add more as needed",
    "Rest of the code",
    "... existing code ...",
    "... your code ...",
    "Your code here",
]

COMMENT_MARKERS = {
    ".py": "#",
    ".js": ("//", "/*"),
    ".ts": ("//", "/*"),
    ".tsx": ("//", "/*"),
    ".jsx": ("//", "/*"),
    ".mjs": ("//", "/*"),
    ".sh": "#",
    ".bash": "#",
    ".css": "/*",
    ".go": "//",
    ".rs": ("//", "/*"),
    ".java": ("//", "/*"),
    ".c": ("//", "/*"),
    ".cpp": ("//", "/*"),
    ".cc": ("//", "/*"),
    ".cs": ("//", "/*"),
    ".rb": "#",
    ".yaml": "#",
    ".yml": "#",
    ".toml": "#",
}

EMOJI_PATTERN = re.compile(
    r"[\U0001F300-\U0001F9FF]|[☀-➿]|[\U0001F600-\U0001F64F]|[\U0001F900-\U0001F9FF]",
    flags=re.UNICODE
)


def get_file_extension(path: str) -> str:
    p = Path(path)
    return p.suffix.lower()


def is_comment_line(line: str, markers) -> bool:
    stripped = line.lstrip()
    if isinstance(markers, str):
        return stripped.startswith(markers)
    if isinstance(markers, tuple):
        return any(stripped.startswith(m) for m in markers)
    return False


def is_boilerplate_line(line: str, markers=None) -> bool:
    stripped = line.strip()
    if not stripped:
        return False

    comment_text = stripped
    if markers:
        if isinstance(markers, str):
            if comment_text.startswith(markers):
                comment_text = comment_text[len(markers):].lstrip()
        elif isinstance(markers, tuple):
            for m in markers:
                if comment_text.startswith(m):
                    comment_text = comment_text[len(m):].lstrip()
                    break

    comment_lower = comment_text.lower()
    for phrase in LLM_BOILERPLATE:
        if comment_lower == phrase.lower() or comment_lower == phrase.rstrip(':').lower():
            return True
    return False


def humanize_file(path: str) -> dict:
    result = {"file": path, "dashes": 0, "quotes": 0, "ellipsis": 0, "emoji": 0, "boilerplate": 0}
    try:
        p = Path(path)
        if p.is_symlink():
            return result
        if not p.is_file():
            return result
        try:
            original = p.read_bytes()
        except (OSError, PermissionError):
            return result

        if b"\0" in original[:8192]:
            return result

        try:
            text = original.decode("utf-8")
        except UnicodeDecodeError:
            return result

        ext = get_file_extension(path)
        markers = COMMENT_MARKERS.get(ext)
        if markers is None:
            return result

        lines = text.split("\n")
        new_lines = []

        for line in lines:
            new_line = line
            is_comment = is_comment_line(line, markers)

            if is_comment:
                if is_boilerplate_line(new_line, markers):
                    new_line = ""
                    result["boilerplate"] += 1
                else:
                    result["dashes"] += line.count("—") + line.count("–") + line.count("―")
                    new_line = new_line.translate(DASHES)

                    result["quotes"] += sum(1 for c in line if c in "‘’“”")
                    new_line = new_line.translate(CURLY_QUOTES)

                    result["ellipsis"] += line.count(ELLIPSIS)
                    new_line = new_line.replace(ELLIPSIS, "...")

                    result["emoji"] += len(EMOJI_PATTERN.findall(line))
                    new_line = EMOJI_PATTERN.sub("", new_line)

            new_lines.append(new_line)

        new_text = "\n".join(new_lines)
        if new_text == text:
            return result

        mode = p.stat().st_mode
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(new_text.encode("utf-8"))
        os.replace(str(tmp), str(p))
        p.chmod(mode)

        result["changed"] = True
        return result
    except Exception as e:
        print(f"humanize: error processing {path}: {e}", file=sys.stderr)
        return result


def report_result(result: dict) -> None:
    if not result.get("changed"):
        return
    parts = []
    if result.get("boilerplate"):
        parts.append(f"{result['boilerplate']} boilerplate")
    if result.get("dashes"):
        parts.append(f"{result['dashes']} dashes")
    if result.get("quotes"):
        parts.append(f"{result['quotes']} quotes")
    if result.get("ellipsis"):
        parts.append(f"{result['ellipsis']} ellipsis")
    if result.get("emoji"):
        parts.append(f"{result['emoji']} emoji")

    msg = f"humanize: {result['file']}: fixed {', '.join(parts)}"
    print(msg, file=sys.stderr)


def cli(args) -> int:
    if not args.path:
        return 0

    for path_str in args.path:
        p = Path(path_str)
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and not f.is_symlink():
                    result = humanize_file(str(f))
                    if args.check and result.get("changed"):
                        report_result(result)
        else:
            result = humanize_file(path_str)
            if args.check and result.get("changed"):
                report_result(result)
    return 0
