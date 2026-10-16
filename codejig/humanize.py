import io
import os
import re
import sys
import tokenize
from pathlib import Path

from codejig.atomicwrite import atomic_write, resolve_inside

DASHES = str.maketrans({"—": "-", "–": "-", "―": "-"})
CURLY_QUOTES = str.maketrans({
    "‘": "'", "’": "'",
    "“": '"', "”": '"',
})
ELLIPSIS = "…"

LLM_BOILERPLATE = [
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

BOILERPLATE_PATTERN = re.compile(
    r"(?:certainly[!.,]?\s*$|(?:" + "|".join(re.escape(p) for p in LLM_BOILERPLATE) + r")(?![\w']))",
    re.IGNORECASE,
)

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

    return BOILERPLATE_PATTERN.match(comment_text) is not None


def python_comment_lines(text: str) -> set[int] | None:
    """0-based numbers of lines that hold only a comment, read by the tokenizer so
    a `#` inside a string literal is never mistaken for one. None if it cannot parse."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return None
    lines = text.split("\n")
    return {
        t.start[0] - 1
        for t in tokens
        if t.type == tokenize.COMMENT and not lines[t.start[0] - 1][: t.start[1]].strip()
    }


def humanize_text(text: str, markers, comment_lines: set[int] | None = None) -> tuple[str, dict]:
    counts = {"dashes": 0, "quotes": 0, "ellipsis": 0, "emoji": 0, "boilerplate": 0}
    kept = []
    for number, line in enumerate(text.split("\n")):
        is_comment = number in comment_lines if comment_lines is not None else is_comment_line(line, markers)
        if not is_comment:
            kept.append(line)
            continue
        if is_boilerplate_line(line, markers):
            counts["boilerplate"] += 1
            continue
        counts["dashes"] += sum(line.count(d) for d in "—–―")
        counts["quotes"] += sum(1 for c in line if c in "‘’“”")
        counts["ellipsis"] += line.count(ELLIPSIS)
        counts["emoji"] += len(EMOJI_PATTERN.findall(line))
        line = EMOJI_PATTERN.sub("", line.translate(DASHES).translate(CURLY_QUOTES).replace(ELLIPSIS, "..."))
        kept.append(line)
    return "\n".join(kept), counts


def humanize_file(path: str, root: str | None = None, write: bool = True) -> dict:
    result = {"file": path, "dashes": 0, "quotes": 0, "ellipsis": 0, "emoji": 0, "boilerplate": 0}
    markers = COMMENT_MARKERS.get(get_file_extension(path))
    target = resolve_inside(path, root)
    if markers is None or target is None:
        return result
    try:
        original = target.read_bytes()
        if b"\0" in original[:8192]:
            return result
        text = original.decode("utf-8")
        comment_lines = None
        if target.suffix.lower() == ".py":
            comment_lines = python_comment_lines(text)
            if comment_lines is None:
                return result
        new_text, counts = humanize_text(text, markers, comment_lines)
        result.update(counts)
        if new_text != text:
            result["changed"] = True
            if write:
                atomic_write(target, new_text.encode("utf-8"))
    except UnicodeDecodeError:
        return result
    except Exception as e:
        print(f"humanize: error processing {path}: {e}", file=sys.stderr)
    return result


def report_result(result: dict) -> str | None:
    if not result.get("changed"):
        return None
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
    return msg


SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}


def _files(root: Path):
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            yield Path(dirpath) / name


def cli(args) -> int:
    changed = 0
    for path_str in args.path or []:
        start = Path(path_str).resolve()
        root = start if start.is_dir() else start.parent
        for f in _files(start):
            result = humanize_file(str(f), root=str(root), write=not args.check)
            if result.get("changed"):
                changed += 1
                report_result(result)
    return 1 if args.check and changed else 0
