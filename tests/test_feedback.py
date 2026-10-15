import json
import os
import shutil
import sys
import unittest
from io import StringIO
from unittest import mock

from harness import feedback, hooks
from tests.util import tree, write

HAS_RUFF = shutil.which("ruff") is not None


def run_hook(payload: dict) -> str:
    stdin, stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = StringIO(json.dumps(payload)), StringIO()
    try:
        hooks.handle_posttooluse()
        return sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = stdin, stdout


class Lint(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_clean_files_say_nothing(self):
        for name, text in (("a.py", "x = 1\n"), ("a.json", '{"a": 1}\n'), ("a.toml", "a = 1\n"), ("a.md", "{{\n")):
            path = write(self.root / name, text)
            self.assertIsNone(feedback.lint(str(path), str(self.root)), name)

    def test_python_syntax_error_without_ruff(self):
        path = write(self.root / "pkg" / "a.py", "def f(:\n")
        with mock.patch.object(feedback.shutil, "which", return_value=None):
            note = feedback.lint(str(path), str(self.root))
        self.assertIn("pkg/a.py:1:", note)
        self.assertIn("SyntaxError", note)

    @unittest.skipUnless(HAS_RUFF, "ruff not on PATH")
    def test_python_undefined_name_with_ruff(self):
        path = write(self.root / "a.py", "def f():\n    return undefined_name\n")
        note = feedback.lint(str(path), str(self.root))
        self.assertIn("F821", note)
        self.assertIn("a.py:2:", note)
        self.assertFalse((self.root / ".ruff_cache").exists())

    @unittest.skipUnless(HAS_RUFF, "ruff not on PATH")
    def test_a_file_name_is_never_read_as_an_option(self):
        path = write(self.root / "--output-file=written.py", "def f():\n    return undefined_name\n")
        note = feedback.lint(str(path), str(self.root))
        self.assertFalse((self.root / "written.py").exists())
        self.assertIn("F821", note)

    @unittest.skipUnless(HAS_RUFF, "ruff not on PATH")
    def test_repo_ruff_config_is_ignored(self):
        write(self.root / "pyproject.toml", '[tool.ruff.lint]\nselect = ["D"]\n')
        path = write(self.root / "a.py", "x = 1\n")
        self.assertIsNone(feedback.lint(str(path), str(self.root)))

    @unittest.skipIf(os.name == "nt", "POSIX shell script")
    def test_ruff_inside_the_workspace_is_never_run(self):
        fake = write(self.root / "bin" / "ruff", "#!/bin/sh\ntouch ran\n")
        os.chmod(fake, 0o755)
        path = write(self.root / "a.py", "def f(:\n")
        with mock.patch.object(feedback.shutil, "which", return_value=str(fake)):
            note = feedback.lint(str(path), str(self.root))
        self.assertIn("SyntaxError", note)
        self.assertFalse((self.root / "ran").exists())

    def test_json_and_toml_errors(self):
        j = write(self.root / "a.json", '{"a": }\n')
        t = write(self.root / "a.toml", "a = \n")
        self.assertIn("a.json:1:", feedback.lint(str(j), str(self.root)))
        self.assertIn("a.toml", feedback.lint(str(t), str(self.root)))

    def test_output_is_capped(self):
        text = feedback.cap([f"a.py:{i}:1: F821 x" for i in range(30)])
        self.assertEqual(len(text.splitlines()), feedback.MAX_LINES + 1)
        self.assertTrue(text.endswith("20 more"))

    def test_outside_root_is_skipped(self):
        outside = write(self.root.parent / "out.json", "{\n")
        self.assertIsNone(feedback.lint(str(outside), str(self.root)))

    @unittest.skipIf(os.name == "nt", "symlinks need extra rights on Windows")
    def test_symlink_is_skipped(self):
        outside = write(self.root.parent / "out.json", "{\n")
        link = self.root / "link.json"
        link.symlink_to(outside)
        self.assertIsNone(feedback.lint(str(link), str(self.root)))


PATCH_SKIP = """*** Begin Patch
*** Update File: tests/test_a.py
@@
-def test_a():
+@pytest.mark.skip(reason="flaky")
+def test_a():
*** Update File: src/app.ts
@@
+it.skip("works", () => {});
*** End Patch
"""


class Tamper(unittest.TestCase):
    def test_patch_adding_skips_is_flagged_per_file(self):
        notes = feedback.tamper("apply_patch", {"command": ["apply_patch", PATCH_SKIP]})
        self.assertEqual(len(notes), 2)
        self.assertIn("tests/test_a.py", notes[0])
        self.assertIn("pytest.mark.skip", notes[0])
        self.assertIn("fix the code", notes[0])
        self.assertIn("it.skip", notes[1])

    def test_patch_deleting_a_test_file_is_flagged(self):
        patch = "*** Begin Patch\n*** Delete File: tests/test_a.py\n*** Delete File: src/old.py\n*** End Patch\n"
        [note] = feedback.tamper("apply_patch", {"command": ["apply_patch", patch]})
        self.assertIn("deleted test file tests/test_a.py", note)

    def test_test_file_names_across_stacks(self):
        for p in ("tests/x.py", "test_x.py", "pkg/x_test.go", "src/x.spec.ts", "src/x.test.jsx",
                  "__tests__/x.js", "Api.Tests/FooTests.cs"):
            self.assertTrue(feedback.is_test_path(p), p)
        for p in ("src/app.py", "latest.py", "contest/x.py"):
            self.assertFalse(feedback.is_test_path(p), p)

    def test_removing_a_skip_is_fine(self):
        patch = "*** Begin Patch\n*** Update File: t.py\n@@\n-@pytest.mark.skip\n def test_a():\n*** End Patch\n"
        self.assertEqual(feedback.tamper("apply_patch", {"command": ["apply_patch", patch]}), [])

    def test_claude_edit_compares_old_and_new(self):
        added = {"file_path": "a.test.ts", "old_string": 'it("x", f)', "new_string": 'it.skip("x", f)'}
        kept = {"file_path": "a.test.ts", "old_string": 'xit("x", f)\n', "new_string": 'xit("x", g)\n'}
        self.assertEqual(len(feedback.tamper("Edit", added)), 1)
        self.assertEqual(feedback.tamper("Edit", kept), [])
        multi = {"file_path": "FooTests.cs", "edits": [{"old_string": "[Fact]", "new_string": '[Fact(Skip = "later")]'}]}
        self.assertIn("Skip", feedback.tamper("MultiEdit", multi)[0])

    def test_other_tools_and_junk_say_nothing(self):
        for name, ti in (("Read", {"file_path": "t.py"}), ("apply_patch", "junk"), ("Edit", None), ("Bash", {"command": "it.skip("})):
            self.assertEqual(feedback.tamper(name, ti), [])


class Hook(unittest.TestCase):
    def test_hook_reports_lint_and_tamper_to_the_model(self):
        root = tree(self)
        write(root / "tests" / "test_a.py", "@pytest.mark.skip\ndef test_a(:\n")
        out = run_hook({"cwd": str(root), "tool_name": "apply_patch",
                        "tool_input": {"command": ["apply_patch", PATCH_SKIP]}})
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("lint: tests/test_a.py", context)
        self.assertIn("tests: tests/test_a.py", context)

    def test_clean_write_stays_silent(self):
        root = tree(self)
        path = write(root / "a.py", "x = 1\n")
        self.assertEqual(run_hook({"cwd": str(root), "tool_name": "Write", "tool_input": {"file_path": str(path)}}), "")


if __name__ == "__main__":
    unittest.main()
