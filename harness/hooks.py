import json
import re
import sys

from harness.humanize import humanize_file
from harness.humanize import report_result as report_humanize
from harness.watermark import report_result as report_watermark
from harness.watermark import strip_watermark

PATCH_PATH = re.compile(r"^\*\*\* (?:Add File|Update File|Move to): (.+?)\s*$", re.MULTILINE)


def changed_paths(tool_input: object) -> list[str]:
    """Files a tool call wrote: `file_path`/`path` keys, or the targets of an apply_patch body."""
    found: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("file_path", "path", "notebook_path") and isinstance(item, str):
                    found.append(item)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            found.extend(PATCH_PATH.findall(value))

    walk(tool_input)
    return list(dict.fromkeys(found))


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
        notes = clean(changed_paths(payload.get("tool_input")), payload.get("cwd"))
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
