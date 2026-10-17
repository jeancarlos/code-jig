import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "fixes_have_tests.py"
spec = importlib.util.spec_from_file_location("fixes_have_tests", SCRIPT)
fixes_have_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixes_have_tests)
missing_tests = fixes_have_tests.missing_tests


class MissingTests(unittest.TestCase):
    def test_fix_and_feat_without_a_test_are_named(self):
        out = missing_tests([("fix: stop it", "", ["codejig/a.py"]), ("feat(x)!: new", "", ["codejig/b.py"])])
        self.assertEqual(len(out), 2)
        self.assertIn("No-Test", out[0])

    def test_fix_touching_tests_passes(self):
        self.assertEqual(missing_tests([("fix: x", "", ["codejig/a.py", "tests/test_a.py"])]), [])

    def test_other_types_need_no_test(self):
        changes = [("chore: x", "", ["a.py"]), ("ci: x", "", []), ("docs: x", "", ["README.md"]), ("Fixes typo", "", ["a.py"])]
        self.assertEqual(missing_tests(changes), [])

    def test_no_test_line_needs_a_reason(self):
        self.assertEqual(missing_tests([("fix: x", "No-Test: wording only", ["a.py"])]), [])
        self.assertEqual(len(missing_tests([("fix: x", "No-Test:", ["a.py"])])), 1)


class Cli(unittest.TestCase):
    def run_cli(self, repo, base):
        return subprocess.run([sys.executable, str(SCRIPT), base, "HEAD"], check=False, cwd=repo, capture_output=True, text=True)

    def commit(self, repo, message, files):
        for name in files:
            path = Path(repo, name)
            path.parent.mkdir(exist_ok=True)
            path.write_text(message, encoding="utf-8")
        cfg = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", *cfg, "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", *cfg, "commit", "-q", "--allow-empty", "-m", message], cwd=repo, check=True)

    def test_range_fails_on_an_untested_fix_and_passes_with_a_test(self):
        with tempfile.TemporaryDirectory() as repo:
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            self.commit(repo, "chore: base", ["a.py"])
            base = subprocess.run(["git", "rev-parse", "HEAD"], check=False, cwd=repo, capture_output=True, text=True).stdout.strip()
            self.commit(repo, "fix: broken", ["a.py"])
            failed = self.run_cli(repo, base)
            self.assertEqual(failed.returncode, 1)
            self.assertIn("fix: broken", failed.stderr)
            subprocess.run(["git", "reset", "-q", "--hard", base], cwd=repo, check=True)
            self.commit(repo, "fix: tested", ["tests/test_a.py"])
            self.assertEqual(self.run_cli(repo, base).returncode, 0)


if __name__ == "__main__":
    unittest.main()
