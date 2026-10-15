import ast
import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from harness.atomicwrite import resolve_inside

MAX_LINES = 10
MAX_BYTES = 1_000_000
RUFF_SELECT = "E9,F63,F7,F82"
DELETE_PATH = re.compile(r"^\*\*\* Delete File: (.+?)\s*$", re.MULTILINE)
FILE_HEADER = re.compile(r"^\*\*\* (?:Add File|Update File|Move to): (.+?)\s*$")
TEST_PATH = re.compile(
    r"(?:^|/)(?:tests?|__tests__|specs?)/"
    r"|(?:^|/)test_[^/]*\.py$"
    r"|_test\.(?:py|go)$"
    r"|\.(?:test|spec)\.[cm]?[jt]sx?$"
    r"|Tests?\.cs$"
    r"|\.Tests?/"
)
SKIP_MARKER = re.compile(
    r"@pytest\.mark\.(?:skip|skipif|xfail)\b"
    r"|\bpytest\.skip\("
    r"|@unittest\.(?:skip|skipIf|skipUnless|expectedFailure)\b"
    r"|\b(?:it|test|describe)\.(?:skip|todo)\("
    r"|\bx(?:it|describe|test)\("
    r"|\[(?:Fact|Theory|Test)\([^)\]]*\bSkip\s*="
    r"|\[Ignore\b"
    r"|\bAssert\.Inconclusive\("
    r"|@(?:Disabled|Ignore)\b"
    r"|\bt\.Skip(?:Now)?\("
)


def patch_bodies(tool_input: object) -> list[str]:
    values = tool_input.values() if isinstance(tool_input, dict) else [tool_input]
    bodies = []
    for value in values:
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, str) and item.lstrip().startswith("*** Begin Patch"):
                bodies.append(item)
    return bodies


def cap(lines: list[str]) -> str:
    shown = lines[:MAX_LINES]
    if len(lines) > MAX_LINES:
        shown.append(f"... {len(lines) - MAX_LINES} more")
    return "\n".join(shown)


def _ruff(root: Path) -> str | None:
    found = shutil.which("ruff")
    if not found or Path(os.path.realpath(found)).is_relative_to(root):
        return None
    return found


def _python(real: Path, rel: str, text: str, root: Path) -> list[str]:
    ruff = _ruff(root)
    if ruff:
        try:
            r = subprocess.run([ruff, "check", "--isolated", "--no-cache", "--quiet", "--no-fix",
                                "--output-format", "concise", "--select", RUFF_SELECT, "--", rel],
                               cwd=root, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=5, stdin=subprocess.DEVNULL)
            if r.returncode in (0, 1):
                return [ln for ln in r.stdout.splitlines() if ln.strip()]
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        ast.parse(text, filename=rel)
    except SyntaxError as e:
        return [f"{rel}:{e.lineno}:{e.offset}: SyntaxError {e.msg}"]
    return []


def _json(rel: str, text: str) -> list[str]:
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        return [f"{rel}:{e.lineno}:{e.colno}: {e.msg}"]
    return []


def _toml(rel: str, text: str) -> list[str]:
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return [f"{rel}: {e}"]
    return []


def lint(path: str, root: str | None) -> str | None:
    """Errors in a file the agent just wrote, or None when it is clean or not checkable.

    Only parsers that never run repository code: ruff with no config and a fixed
    rule set, or the standard library. The file must be a regular file inside root.
    """
    base = Path(os.path.realpath(root if root is not None else os.getcwd()))
    real = resolve_inside(path, base)
    if real is None or real.suffix not in (".py", ".json", ".toml") or real.stat().st_size > MAX_BYTES:
        return None
    try:
        text = real.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    rel = real.relative_to(base).as_posix()
    if real.suffix == ".py":
        found = _python(real, rel, text, base)
    elif real.suffix == ".json":
        found = _json(rel, text)
    else:
        found = _toml(rel, text)
    return f"lint: {rel}\n{cap(found)}" if found else None


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH.search(path.replace("\\", "/")))


def _note(path: str, what: str) -> str:
    return (f"tests: {path}: {what}. Unless the user asked for this, restore the test "
            f"and fix the code instead.")


def _patch_notes(body: str) -> list[str]:
    notes = [_note(p, f"deleted test file {p}") for p in DELETE_PATH.findall(body) if is_test_path(p)]
    current, added = None, {}
    for line in body.splitlines():
        header = FILE_HEADER.match(line)
        if header:
            current = header.group(1)
        elif current and line.startswith("+"):
            for m in SKIP_MARKER.finditer(line):
                added.setdefault(current, []).append(m.group(0))
    notes += [_note(p, "added " + ", ".join(dict.fromkeys(ms))) for p, ms in added.items()]
    return notes


def _edit_notes(path: str, pairs: list[tuple[str, str]]) -> list[str]:
    found = []
    for old, new in pairs:
        before = {m.group(0) for m in SKIP_MARKER.finditer(old)}
        found += [m.group(0) for m in SKIP_MARKER.finditer(new) if m.group(0) not in before]
    return [_note(path, "added " + ", ".join(dict.fromkeys(found)))] if found else []


def _edit_pairs(tool_name: object, tool_input: dict) -> list[tuple[str, str]]:
    edits = tool_input.get("edits") if tool_name == "MultiEdit" else [tool_input]
    pairs = [(e.get("old_string") or "", e.get("new_string") or "") for e in edits or [] if isinstance(e, dict)]
    return [(o, n) for o, n in pairs if isinstance(o, str) and isinstance(n, str)]


def tamper(tool_name: object, tool_input: object) -> list[str]:
    """Notices for a write that deletes a test file or adds a skip marker."""
    if tool_name == "apply_patch":
        return [n for body in patch_bodies(tool_input) for n in _patch_notes(body)]
    if tool_name in ("Edit", "MultiEdit") and isinstance(tool_input, dict) and isinstance(tool_input.get("file_path"), str):
        return _edit_notes(tool_input["file_path"], _edit_pairs(tool_name, tool_input))
    return []
