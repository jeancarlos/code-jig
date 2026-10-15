import json
import re
import sys

from harness.humanize import humanize_file
from harness.humanize import report_result as report_humanize
from harness.watermark import report_result as report_watermark
from harness.watermark import strip_watermark

PATCH_PATH = re.compile(r"^\*\*\* (?:Add File|Update File|Move to): (.+?)\s*$", re.MULTILINE)
CLAUDE_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _patch_bodies(tool_input: object) -> list[str]:
    values = tool_input.values() if isinstance(tool_input, dict) else [tool_input]
    bodies = []
    for value in values:
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, str) and item.lstrip().startswith("*** Begin Patch"):
                bodies.append(item)
    return bodies


def changed_paths(tool_name: object, tool_input: object) -> list[str]:
    """Files this tool call wrote, and nothing else.

    Claude Code's write tools name their file; Codex's apply_patch names its
    targets inside the patch argument. Every other tool, including ones that
    merely read a `path`, gives an empty list.
    """
    if tool_name in CLAUDE_WRITE_TOOLS and isinstance(tool_input, dict):
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        return [path] if isinstance(path, str) else []
    if tool_name == "apply_patch":
        found = [p for body in _patch_bodies(tool_input) for p in PATCH_PATH.findall(body)]
        return list(dict.fromkeys(found))
    return []


def clean(paths: list[str], root: str | None) -> list[str]:
    notes = []
    for path in paths:
        for note in (
            report_watermark(strip_watermark(path, root)),
            report_humanize(humanize_file(path, root)),
        ):
            if note:
                notes.append(note)
    return notes


def handle_posttooluse() -> int:
    """PostToolUse for Claude Code and Codex: clean what the tool wrote, then say what changed."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        notes = clean(changed_paths(payload.get("tool_name"), payload.get("tool_input")), payload.get("cwd"))
        if notes:
            msg = "; ".join(notes)
            sys.stdout.write(json.dumps({
                "systemMessage": msg,
                "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg},
            }) + "\n")
    except Exception as e:
        print(f"watermark: hook error: {e}", file=sys.stderr)
    return 0


def cli(args) -> int:
    return handle_posttooluse()
