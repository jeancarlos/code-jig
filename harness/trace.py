from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from harness.analyze import printable, source_files

TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|specs?)/"
    r"|\.(test|spec)\.[cm]?[jt]sx?$"
    r"|(^|/)test_[^/]*\.py$"
    r"|_test\.py$"
    r"|Tests?\.cs$"
    r"|(^|/)[^/]*\.Tests?/"
)
ID_CHARS = r"[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)*"
MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class Result:
    covered: dict[str, list[str]]
    missing: list[str]
    unknown: dict[str, list[str]]


def _norm(value) -> str:
    text = str(value).strip().lstrip("#")
    return text[4:] if text.lower().startswith("req-") else text


def _json_ids(data) -> list:
    if isinstance(data, dict):
        data = data.get("workItems") or data.get("value") or ([data] if "id" in data else [])
    if isinstance(data, (int, str)) and not isinstance(data, bool):
        return [data]
    if not isinstance(data, list):
        return []
    return [item.get("id") if isinstance(item, dict) else item for item in data if not isinstance(item, (list, bool))]


def read_ids(text: str) -> list[str]:
    try:
        raw = _json_ids(json.loads(text))
    except ValueError:
        raw = [line.split()[0] for line in text.splitlines() if line.strip()]
    ids = [_norm(v) for v in raw if v is not None and _norm(v)]
    return list(dict.fromkeys(ids))


def _regex(pattern: str, id_part: str) -> re.Pattern:
    if "{id}" not in pattern:
        raise ValueError("pattern must contain {id}")
    head, _, tail = pattern.partition("{id}")
    return re.compile(rf"(?<![\w-]){head}{id_part}{tail}(?!\w|[.-]\w)", re.IGNORECASE)


def trace(root: Path, ids: list[str], pattern: str = "REQ-{id}") -> Result:
    wanted = {i.lower(): i for i in ids}
    finder = _regex(pattern, f"({ID_CHARS})")
    covered: dict[str, list[str]] = {}
    unknown: dict[str, list[str]] = {}
    for name in source_files(root):
        if not TEST_PATH.search(name):
            continue
        f = root / name
        if f.stat().st_size > MAX_BYTES:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for found in dict.fromkeys(m.group(1) for m in finder.finditer(text)):
            target = covered if found.lower() in wanted else unknown
            key = wanted.get(found.lower(), found)
            if name not in target.setdefault(key, []):
                target[key].append(name)
    ordered = {i: covered[i] for i in ids if i in covered}
    return Result(ordered, [i for i in ids if i not in covered], dict(sorted(unknown.items())))


def _files(names: list[str], limit: int = 3) -> str:
    extra = f" and {len(names) - limit} more" if len(names) > limit else ""
    return printable(", ".join(names[:limit]) + extra)


def render(result: Result) -> list[str]:
    total = len(result.covered) + len(result.missing)
    out = [f"trace: {len(result.covered)} of {total} requirements have tests"]
    out += [f"  {printable(i)}  {_files(names)}" for i, names in result.covered.items()]
    if result.missing:
        out.append(f"missing: {printable(', '.join(result.missing))}")
    out += [f"unknown in tests: {printable(i)} ({_files(names)})" for i, names in result.unknown.items()]
    return out


def cli(args) -> int:
    try:
        text = sys.stdin.read() if args.ids == "-" else Path(args.ids).read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"harness: {args.ids}: {e.strerror or e}", file=sys.stderr)
        return 2
    ids = read_ids(text)
    if not ids:
        print(f"harness: no requirement IDs in {args.ids}", file=sys.stderr)
        return 2
    try:
        result = trace(Path(args.path).resolve(), ids, args.pattern)
    except (ValueError, re.error) as e:
        print(f"harness: --pattern: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"covered": result.covered, "missing": result.missing, "unknown": result.unknown}, ensure_ascii=False, indent=1))
    else:
        for line in render(result):
            print(line)
    return 1 if result.missing or result.unknown else 0
