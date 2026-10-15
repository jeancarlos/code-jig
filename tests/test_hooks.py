import json
import os
import stat
import sys
import unittest
from argparse import Namespace
from io import StringIO

from harness import hooks
from harness.atomicwrite import atomic_write, resolve_inside
from harness.humanize import cli as humanize_cli
from tests.util import tree, write


def run_hook(payload: object) -> tuple[int, str]:
    stdin, stdout = sys.stdin, sys.stdout
    sys.stdin = StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    sys.stdout = StringIO()
    try:
        code = hooks.handle_posttooluse()
        return code, sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = stdin, stdout


class PostToolUseHook(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_claude_code_write_is_cleaned_and_reported_to_the_model(self):
        path = write(self.root / "a.py", "x = 1\n# Certainly\nCo-Authored-By: Claude <x@y>\n")
        code, out = run_hook({"cwd": str(self.root), "tool_name": "Write", "tool_input": {"file_path": str(path)}})
        self.assertEqual(code, 0)
        self.assertEqual(path.read_text(encoding="utf-8"), "x = 1\n")
        report = json.loads(out)
        self.assertEqual(report["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("attribution", report["systemMessage"])
        self.assertIn("boilerplate", report["hookSpecificOutput"]["additionalContext"])

    def test_codex_apply_patch_targets_are_cleaned(self):
        added = write(self.root / "new.py", "# done — ok\n")
        moved = write(self.root / "sub" / "moved.py", "y = 2\n")
        patch = "*** Begin Patch\n*** Add File: new.py\n+x\n*** Update File: old.py\n*** Move to: sub/moved.py\n*** End Patch\n"
        code, out = run_hook({"cwd": str(self.root), "tool_name": "apply_patch", "tool_input": {"command": ["apply_patch", patch]}})
        self.assertEqual(code, 0)
        self.assertEqual(added.read_text(encoding="utf-8"), "# done - ok\n")
        self.assertEqual(moved.read_text(encoding="utf-8"), "y = 2\n")
        self.assertIn("new.py", out)

    def test_clean_files_produce_no_output_and_stay_untouched(self):
        path = write(self.root / "a.py", "x = 1\n")
        before = os.stat(path).st_mtime_ns
        _, out = run_hook({"cwd": str(self.root), "tool_input": {"file_path": str(path)}})
        self.assertEqual(out, "")
        self.assertEqual(os.stat(path).st_mtime_ns, before)

    def test_bad_input_never_fails_the_tool_call(self):
        self.assertEqual(run_hook("{not json")[0], 0)
        self.assertEqual(run_hook({"tool_input": {}})[0], 0)

    def test_files_outside_the_session_root_are_left_alone(self):
        outside = write(self.root.parent / "outside.py", "x\n")
        run_hook({"cwd": str(self.root), "tool_input": {"file_path": str(outside)}})
        self.assertEqual(outside.read_text(encoding="utf-8"), "x\n")


class SafeWrites(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_a_sibling_that_shares_the_root_prefix_is_outside(self):
        sibling = write(self.root.parent / (self.root.name + "-evil") / "a.py", "x\n")
        self.assertIsNone(resolve_inside(str(sibling), self.root))

    def test_symlinks_and_directories_are_refused(self):
        target = write(self.root / "real.py", "x\n")
        link = self.root / "link.py"
        link.symlink_to(target)
        self.assertIsNone(resolve_inside(str(link), self.root))
        self.assertIsNone(resolve_inside(str(self.root), self.root))
        self.assertEqual(resolve_inside("real.py", self.root), target.resolve())

    def test_atomic_write_keeps_mode_and_leaves_no_temp(self):
        path = write(self.root / "a.sh", "old\n")
        os.chmod(path, 0o750)
        atomic_write(path, b"new\n")
        self.assertEqual(path.read_bytes(), b"new\n")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o750)
        self.assertEqual([p.name for p in self.root.iterdir()], ["a.sh"])


class HumanizeCli(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_check_reports_without_writing_and_skips_vendored_dirs(self):
        src = write(self.root / "a.py", "# Here is the updated code\nx = 1\n")
        vendored = write(self.root / "node_modules" / "b.js", "// Certainly\n")
        self.assertEqual(humanize_cli(Namespace(path=[str(self.root)], check=True)), 1)
        self.assertEqual(src.read_text(encoding="utf-8"), "# Here is the updated code\nx = 1\n")
        self.assertEqual(humanize_cli(Namespace(path=[str(self.root)], check=False)), 0)
        self.assertEqual(src.read_text(encoding="utf-8"), "x = 1\n")
        self.assertEqual(vendored.read_text(encoding="utf-8"), "// Certainly\n")


if __name__ == "__main__":
    unittest.main()
