# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import re
from pathlib import Path

NAME = re.compile(r"[a-zA-Z0-9-]{1,64}")
FORCE_LOAD = re.compile(r"(?<![\w`])@[\w./-]*(?:skills?/|SKILL\.md)[\w./-]*")
DATE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")
CODE_BLOCK = re.compile(r"```[\w-]*\n(.*?)```", re.DOTALL)
FOLDED = {">", ">-", ">+", "|", "|-", "|+"}


def _split(text: str) -> tuple[list[str], str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return (lines[1:i], "\n".join(lines[i + 1:])) if i > 1 else None
    return None


def _field(fm: list[str], key: str) -> str | None:
    for i, line in enumerate(fm):
        if line.startswith(f"{key}:"):
            value = line[len(key) + 1:].strip()
            if value in FOLDED or not value:
                rest = [ln.strip() for ln in fm[i + 1:] if ln.startswith((" ", "\t"))]
                value = " ".join(rest)
            return " ".join(value.strip("\"'").split())
    return None


def _description(desc: str | None) -> list[tuple[str, str]]:
    if not desc:
        return [("FAIL", "frontmatter has no `description`; Codex skips the skill")]
    out = []
    spoken = re.sub(r'"[^"]*"', "", desc)
    if not desc.lower().startswith("use when"):
        out.append(("FAIL", 'description must start with "Use when": it states triggers, not what the skill is'))
    if re.search(r"\b(I|we|my|our)\b", spoken):
        out.append(("FAIL", "description must be third person (found a first-person pronoun)"))
    if re.search(r"\byou\b", spoken, re.IGNORECASE):
        out.append(("WARN", "description addresses the reader as `you`; write it in the third person"))
    if len(desc) > 500:
        out.append(("WARN", f"description is {len(desc)} chars; it is sent with every request, aim under 500"))
    return out


def _body(body: str) -> list[tuple[str, str]]:
    out = []
    words = len(body.split())
    if words > 500:
        out.append(("WARN", f"body is {words} words; aim under 500 and move heavy reference to its own file"))
    out += [("FAIL", f"`{link}` force-loads a file into context; name the skill instead") for link in FORCE_LOAD.findall(body)]
    out += [("WARN", f"date {d} in the body reads as a log; skills are reference") for d in sorted(set(DATE.findall(body)))]
    if not re.search(r"^## Common mistakes", body, re.MULTILINE | re.IGNORECASE):
        out.append(("WARN", "no `## Common mistakes` section"))
    for block in CODE_BLOCK.findall(body):
        n = len(block.splitlines())
        if n > 50:
            out.append(("WARN", f"a {n}-line code block is inline; move blocks over 50 lines to their own file"))
    return out


def check(path: Path) -> list[tuple[str, str]]:
    """Mechanical findings for one SKILL.md: FAIL breaks loading or a hard rule, WARN is a judgement call."""
    parts = _split(path.read_text(encoding="utf-8-sig", errors="replace"))
    if parts is None:
        return [("FAIL", "no frontmatter: the file must start with a `---` line and close it with another")]
    fm, body = parts
    out = []
    name = _field(fm, "name")
    if not name:
        out.append(("FAIL", "frontmatter has no `name`"))
    elif not NAME.fullmatch(name):
        out.append(("FAIL", f"name `{name}` must be 1-64 letters, numbers and hyphens"))
    elif name != path.parent.name:
        out.append(("WARN", f"name `{name}` differs from the directory `{path.parent.name}`"))
    out += _description(_field(fm, "description"))
    size = sum(len(line) + 1 for line in fm) + 8
    if size > 1024:
        out.append(("FAIL", f"frontmatter is {size} chars; Claude Code rejects more than 1024"))
    return out + _body(body)


def cli(args) -> int:
    bad = False
    for arg in args.path or ["."]:
        p = Path(arg)
        target = p if p.is_file() else p / "SKILL.md"
        if not target.is_file():
            print(f"{target}: FAIL file not found")
            bad = True
            continue
        found = check(target)
        print(target)
        for level, msg in found or [("ok", "no mechanical issues")]:
            print(f"  {level} {msg}")
        bad |= any(level == "FAIL" for level, _ in found)
    return 1 if bad else 0
