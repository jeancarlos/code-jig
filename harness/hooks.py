import json
import sys
from pathlib import Path

from harness.watermark import report_result as report_watermark, strip_watermark
from harness.humanize import humanize_file, report_result as report_humanize


def handle_claude_code_posttooluse() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        tool_input = payload.get("tool_input", {})
        file_path = tool_input.get("file_path")
        if file_path:
            result = strip_watermark(file_path)
            report_watermark(result, "claude-code")
            result = humanize_file(file_path)
            report_humanize(result)
    except Exception as e:
        print(f"watermark: hook error: {e}", file=sys.stderr)
    return 0


def handle_codex_collect_wrapper() -> int:
    try:
        data = json.loads(sys.stdin.read())
        for file in data.get("files", []):
            result = strip_watermark(file)
            report_watermark(result, "codex")
            result = humanize_file(file)
            report_humanize(result)
    except Exception:
        pass
    return 0


def cli(args) -> int:
    if args.hook_type == "claude-code":
        return handle_claude_code_posttooluse()
    elif args.hook_type == "codex":
        return handle_codex_collect_wrapper()
    return 0
