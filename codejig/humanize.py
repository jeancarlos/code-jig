import ast
import io
import os
import re
import sys
import tokenize
from pathlib import Path

from codejig.atomicwrite import atomic_write, resolve_inside
from codejig.clike import LANGS, comment_spans

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
    "Of course!",
    "You're absolutely right",
    "Would you like",
    "Is there anything else",
]

NARRATION = r"(?:removed|deleted|new|added|updated|changed|fixed)[.!:]?\s*$|(?:ai|agent|assistant):"
CITATION = re.compile(
    r":?contentReference\[oaicite:\d+\]\{index=\d+\}|\boai_citation:\d+|\[cite:\s*[\d,\s]+\]"
    r"|(?<=[?&])utm_source=(?:chatgpt\.com|openai|copilot\.com)&?|[?&]utm_source=(?:chatgpt\.com|openai|copilot\.com)\b"
)
COUNT_KEYS = ("dashes", "quotes", "ellipsis", "emoji", "boilerplate", "citations")

BOILERPLATE_PATTERN = re.compile(
    r"(?:certainly[!.,]?\s*$|" + NARRATION + r"|(?:" + "|".join(re.escape(p) for p in LLM_BOILERPLATE) + r")(?![\w']))",
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
    if not stripped or (stripped.startswith("/*") and not (stripped.endswith("*/") and stripped.count("*/") == 1)):
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


def python_docstring_lines(text: str) -> dict[int, bool] | None:
    """0-based line number of every docstring line, mapped to True when the line sits between
    the opening and closing delimiter lines, so deleting it cannot touch a delimiter."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    docs = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        first = node.body[0] if node.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            start, end = first.lineno - 1, first.end_lineno - 1
            docs.update({n: start < n < end for n in range(start, end + 1)})
    return docs


def humanize_text(text: str, markers, comment_lines: set[int] | None = None,
                  docs: dict[int, bool] | None = None, doc_quotes: bool = True) -> tuple[str, dict]:
    counts = dict.fromkeys(COUNT_KEYS, 0)
    docs = docs or {}
    kept = []
    for number, line in enumerate(text.split("\n")):
        in_doc = number in docs
        is_comment = number in comment_lines if comment_lines is not None else is_comment_line(line, markers)
        if not (is_comment or in_doc):
            kept.append(line)
            continue
        boilerplate = BOILERPLATE_PATTERN.match(line.strip()) if in_doc and docs[number] else is_comment and is_boilerplate_line(line, markers)
        if boilerplate:
            counts["boilerplate"] += 1
            continue
        kept.append(_scrub(line, counts, doc_quotes or not in_doc))
    return "\n".join(kept), counts


def _scrub(line: str, counts: dict, fix_quotes: bool = True) -> str:
    line, found = CITATION.subn("", line)
    counts["citations"] += found
    counts["dashes"] += sum(line.count(d) for d in "—–―")
    counts["quotes"] += sum(1 for c in line if c in "‘’“”") if fix_quotes else 0
    counts["ellipsis"] += line.count(ELLIPSIS)
    counts["emoji"] += len(EMOJI_PATTERN.findall(line))
    line = line.translate(DASHES).replace(ELLIPSIS, "...")
    return EMOJI_PATTERN.sub("", line.translate(CURLY_QUOTES) if fix_quotes else line)


def _bare(comment: str) -> str:
    return re.sub(r"^(?:/\*+!?|//[/!]?|\*+)\s*|\s*\*/$", "", comment.strip()).strip()


def _span_edits(text: str, start: int, end: int, counts: dict) -> list[tuple[int, int, str]]:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end < 0 else line_end + 1
    alone = not text[line_start:start].strip() and not text[end:line_end].strip()
    pieces = text[start:end].split("\n")
    edits, offset = [], start
    for n, piece in enumerate(pieces):
        interior = 0 < n < len(pieces) - 1
        if (interior or (len(pieces) == 1 and alone)) and BOILERPLATE_PATTERN.match(_bare(piece)):
            counts["boilerplate"] += 1
            cut = (line_start, line_end) if len(pieces) == 1 else (offset, offset + len(piece) + 1)
            edits.append((*cut, ""))
        else:
            edits.append((offset, offset + len(piece), _scrub(piece, counts)))
        offset += len(piece) + 1
    return edits


def clike_text(text: str, lang: str) -> tuple[str, dict]:
    counts = dict.fromkeys(COUNT_KEYS, 0)
    edits = [e for start, end in comment_spans(text, lang) for e in _span_edits(text, start, end, counts)]
    out, pos = [], 0
    for a, b, new in sorted(edits):
        out += [text[pos:a], new]
        pos = b
    return "".join(out) + text[pos:], counts


def _python_pass(text: str, markers, comment_lines: set[int]) -> tuple[str, dict]:
    docs = python_docstring_lines(text)
    new_text, counts = humanize_text(text, markers, comment_lines, docs)
    if new_text != text and docs:
        try:
            ast.parse(new_text)
        except SyntaxError:
            new_text, counts = humanize_text(text, markers, comment_lines, docs, doc_quotes=False)
            try:
                ast.parse(new_text)
            except SyntaxError:
                return humanize_text(text, markers, comment_lines)
    return new_text, counts


def _edited(text: str, suffix: str, markers) -> tuple[str, dict, bool] | None:
    lang = LANGS.get(suffix)
    if lang:
        return (*clike_text(text, lang), True)
    if suffix == ".py":
        comment_lines = python_comment_lines(text)
        return None if comment_lines is None else (*_python_pass(text, markers, comment_lines), True)
    return (*humanize_text(text, markers), False)


def humanize_file(path: str, root: str | None = None, write: bool = True) -> dict:
    result = {"file": path, **dict.fromkeys(COUNT_KEYS, 0)}
    markers = COMMENT_MARKERS.get(get_file_extension(path))
    target = resolve_inside(path, root)
    if markers is None or target is None:
        return result
    try:
        original = target.read_bytes()
        if b"\0" in original[:8192]:
            return result
        text = original.decode("utf-8")
        edited = _edited(text, target.suffix.lower(), markers)
        if edited is None:
            return result
        new_text, counts, editable = edited
        result.update(counts)
        if new_text != text and not editable:
            result["left"] = True
        elif new_text != text:
            result["changed"] = True
            if write:
                atomic_write(target, new_text.encode("utf-8"))
    except UnicodeDecodeError:
        return result
    except Exception as e:
        print(f"humanize: error processing {path}: {e}", file=sys.stderr)
    return result


def report_result(result: dict) -> str | None:
    if not result.get("changed") and not result.get("left"):
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
    if result.get("citations"):
        parts.append(f"{result['citations']} citations")

    msg = f"humanize: {result['file']}: fixed {', '.join(parts)}"
    if result.get("left"):
        msg = (f"humanize: {result['file']}: {', '.join(parts)} in comment-like lines, not changed: only Python comments "
               "are edited, so fix these by hand if they are comments")
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
    if getattr(args, "rewrite", False):
        from codejig import rewrite
        return rewrite.run(args)
    changed = 0
    for path_str in args.path or []:
        start = Path(path_str).resolve()
        root = start if start.is_dir() else start.parent
        for f in _files(start):
            result = humanize_file(str(f), root=str(root), write=not args.check)
            changed += bool(result.get("changed"))
            report_result(result)
    return 1 if args.check and changed else 0
