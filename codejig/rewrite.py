import ast
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from codejig.atomicwrite import atomic_write, resolve_inside
from codejig.clike import LANGS, comment_spans
from codejig.humanize import (
    BOILERPLATE_PATTERN,
    CITATION,
    _files,
    _scrub,
    python_comment_lines,
    python_docstring_lines,
)
from codejig.watermark import ATTRIBUTION, INVISIBLE_CHARS

LOOPBACK = ("127.0.0.1", "localhost", "::1")
DEFAULT_URL = "http://localhost:20128/v1"
DEFAULT_MODEL = "ag/gemini-3.8-flash-high"
PERSONA = (
    "You edit code comments and docstrings so they read like a busy senior engineer wrote them. "
    "Plain words, short sentences, say what is non-obvious or why, never restate the code. "
    "No 'This function' or 'Helper function' openers, no step numbering, no marketing words "
    "(robust, seamless, comprehensive, leverage), no dashes, no emoji, no chat phrases. "
    "Keep every identifier, number, tag (@param, :param) and technical fact exactly. "
    "Use fewer words than the original when the meaning survives."
)
_STRICT = (r"^(?:this (?:function|method|class|module|helper)\b|helper (?:function|method)\b|utility (?:function|to)\b"
           r"|used to\b|step \d+\b|(?:updated|changed|now uses|previously)\b)"
           r"|\b(?:leverag|utiliz|robust|seamless|comprehensive|streamlin)\w*")
STRICT_TELL = re.compile(_STRICT, re.IGNORECASE)
TELL = re.compile(_STRICT + r"|^(?:initialize|define|import|return)s? the \w+$", re.IGNORECASE)
LINE = re.compile(r"^(\s*(?:/\*\*?!?|\*+(?!/)|//[/!]?|#+|[rRuUbB]*(?:\"\"\"|'''))?[ \t]?)(.*?)([ \t]*(?:\*/|\"\"\"|'''))?$")
PRAGMA = re.compile(r"^(?:type:|noqa|pragma|fmt:|pylint|isort|mypy|ruff|eslint|prettier|@ts-|istanbul|c8|biome|spdx|-\*-)", re.IGNORECASE)
MAX_GROWTH = 1.5


def _groups(numbers) -> list[list[int]]:
    out: list[list[int]] = []
    for n in sorted(numbers):
        if out and out[-1][-1] == n - 1:
            out[-1].append(n)
        else:
            out.append([n])
    return out


def _clike_groups(text: str, lang: str) -> list[list[int]]:
    groups: list[list[int]] = []
    after_line_comment = False
    for start, end in comment_spans(text, lang):
        head = text[text.rfind("\n", 0, start) + 1:start]
        newline = text.find("\n", end)
        tail = text[end:] if newline < 0 else text[end:newline]
        if head.strip() or tail.strip():
            continue
        first, last = text.count("\n", 0, start), text.count("\n", 0, end)
        line_comment = first == last and text.startswith("//", start)
        if line_comment and after_line_comment and groups[-1][-1] == first - 1:
            groups[-1].append(first)
        else:
            groups.append(list(range(first, last + 1)))
        after_line_comment = line_comment
    return groups


def _line_groups(text: str, path: str) -> list[list[int]]:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        comments, docs = python_comment_lines(text), python_docstring_lines(text)
        return [] if comments is None or docs is None else _groups(comments) + _groups(docs)
    lang = LANGS.get(suffix)
    return _clike_groups(text, lang) if lang else []


def flagged(text: str, path: str) -> list[list[tuple[int, str, tuple[str, str]]]]:
    lines = text.split("\n")
    found = []
    for group in sorted(_line_groups(text, path)):
        block = []
        for n in group:
            m = LINE.match(lines[n])
            block.append((n, m.group(2), (m.group(1), m.group(3) or "")))
        if any(TELL.search(t) for _, t, _ in block) and not any(PRAGMA.match(t) for _, t, _ in block):
            found.append(block)
    return found


def SAFE(old: str, new: str) -> bool:
    if not old:
        return not new
    if not new.isprintable() or new.endswith("\\") or "??/" in new or '"""' in new or "'''" in new or "*/" in new:
        return False
    if STRICT_TELL.search(new):
        return False
    if any(c in new for c in INVISIBLE_CHARS) or ATTRIBUTION.search(new.encode()) or BOILERPLATE_PATTERN.match(new):
        return False
    if CITATION.search(new) or len(new) > len(old) * MAX_GROWTH + 30:
        return False
    return _scrub(new, dict.fromkeys(("dashes", "quotes", "ellipsis", "emoji", "citations"), 0)) == new


def _block_ok(block, answer) -> bool:
    return (isinstance(answer, list) and len(answer) == len(block) and all(isinstance(a, str) for a in answer)
            and all(SAFE(old, new) for (_, old, _), new in zip(block, answer, strict=True)))


def _apply(lines: list[str], block, answer) -> int:
    if not _block_ok(block, answer):
        return 0
    for (n, _, (head, tail)), new in zip(block, answer, strict=True):
        if new:
            lines[n] = head + new + tail
    return 1


def _skeleton(text: str, path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node, clean=False) is not None:
                node.body[0].value.value = ""
        return ast.dump(tree)
    lang = LANGS.get(suffix)
    if not lang:
        return None
    out, pos = [], 0
    for start, end in comment_spans(text, lang):
        out.append(text[pos:start])
        pos = end
    return "".join(out) + text[pos:]


def rewrite_text(text: str, path: str, ask) -> tuple[str, int]:
    blocks = flagged(text, path)
    if not blocks:
        return text, 0
    answers = ask([[t for _, t, _ in b] for b in blocks])
    if not isinstance(answers, list) or len(answers) != len(blocks):
        return text, 0
    lines = text.split("\n")
    done = sum(_apply(lines, block, answer) for block, answer in zip(blocks, answers, strict=True))
    new_text = "\n".join(lines)
    if done and (_skeleton(new_text, path) is None or _skeleton(new_text, path) != _skeleton(text, path)):
        return text, 0
    return (new_text, done) if done else (text, 0)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def gateway(url: str, model: str, persona: str, key: str | None):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in LOOPBACK):
        raise ValueError(f"gateway URL must be https, or http to this machine: {url}")

    def ask(blocks):
        body = json.dumps({
            "model": model, "temperature": 0.7, "stream": False,
            "messages": [{"role": "system", "content": persona},
                         {"role": "user", "content": json.dumps({"blocks": blocks}, ensure_ascii=False)}],
        }).encode("utf-8")
        headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})}
        req = urllib.request.Request(f"{url.rstrip('/')}/chat/completions", data=body, headers=headers)
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=120) as r:
            content = json.load(r)["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        return json.loads(content)["blocks"]
    return ask


def gateway_url(given: str | None) -> str:
    url = given or os.environ.get("CODEJIG_REWRITE_URL")
    if url:
        return url
    base = os.environ.get("NINEROUTER_URL", "").rstrip("/")
    return DEFAULT_URL if not base else base if base.endswith("/v1") else base + "/v1"


def gateway_key() -> str | None:
    for name in ("CODEJIG_REWRITE_KEY", "NINEROUTER_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        return (Path.home() / ".config" / "9router.key").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _work(paths: list[str]) -> list[tuple]:
    work = []
    for path_str in paths:
        start = Path(path_str).resolve()
        root = start if start.is_dir() else start.parent
        for f in _files(start):
            target = resolve_inside(str(f), str(root))
            try:
                text = target.read_bytes().decode("utf-8") if target else ""
            except (OSError, UnicodeDecodeError):
                continue
            blocks = flagged(text, str(f))
            if blocks:
                work.append((f, target, text, blocks))
    return work


def _confirmed(args) -> int:
    if args.yes:
        return 0
    if not sys.stdin.isatty():
        print("rewrite: refusing to send without a terminal to confirm; pass --yes to allow it", file=sys.stderr)
        return 2
    return 0 if input("send? [y/N] ").strip().lower() == "y" else 2


def _send(work: list[tuple], ask) -> int:
    failed = 0
    for f, target, text, _ in work:
        try:
            new_text, done = rewrite_text(text, str(f), ask)
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as e:
            print(f"rewrite: {f}: {e}", file=sys.stderr)
            failed = 1
            continue
        if done:
            atomic_write(target, new_text.encode("utf-8"))
        print(f"rewrite: {f}: {done} of the flagged blocks rewritten", file=sys.stderr)
    return failed


def run(args) -> int:
    url = gateway_url(args.url)
    model = args.model or DEFAULT_MODEL
    work = _work(args.path or [])
    for f, *_, blocks in work:
        print(f"rewrite: {f}: {len(blocks)} comment blocks flagged", file=sys.stderr)
    if not work or args.check:
        return 0
    sent = sum(len(t) for *_, blocks in work for b in blocks for _, t, _ in b)
    print(f"rewrite: {sent} characters of comment text (no code) would go to {url}, model {model}", file=sys.stderr)
    refused = _confirmed(args)
    if refused:
        return refused
    try:
        persona = Path(args.persona).read_text(encoding="utf-8") if args.persona else PERSONA
        ask = gateway(url, model, persona, gateway_key())
    except (OSError, ValueError) as e:
        print(f"rewrite: {e}", file=sys.stderr)
        return 1
    return _send(work, ask)
