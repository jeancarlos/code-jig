# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "dco.py"
spec = importlib.util.spec_from_file_location("dco", SCRIPT)
dco = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dco)

SIGN = "feat: x\n\nSigned-off-by: Ana Dev <ana@example.org>"


class Unsigned(unittest.TestCase):
    def test_a_commit_signed_off_by_its_author_passes(self):
        self.assertEqual(dco.unsigned([("a" * 40, "Ana Dev", "ana@example.org", "ana@example.org", SIGN)]), [])

    def test_the_email_match_ignores_case(self):
        self.assertEqual(dco.unsigned([("a" * 40, "Ana", "ANA@example.org", "x@y.z", SIGN)]), [])

    def test_a_commit_without_the_line_is_named(self):
        out = dco.unsigned([("b" * 40, "Ana Dev", "ana@example.org", "ana@example.org", "fix: y")])
        self.assertEqual(len(out), 1)
        self.assertIn("bbbbbbbbbbbb", out[0])
        self.assertIn("git commit -s", out[0])

    def test_a_sign_off_by_someone_else_does_not_count(self):
        self.assertEqual(len(dco.unsigned([("c" * 40, "Bo", "bo@example.org", "bo@example.org", SIGN)])), 1)

    def test_the_committer_may_sign_off_for_the_author(self):
        self.assertEqual(dco.unsigned([("d" * 40, "Bo", "bo@example.org", "ana@example.org", SIGN)]), [])

    def test_bots_are_exempt(self):
        bots = [("e" * 40, "dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com", "noreply@github.com", "chore(deps): bump"),
                ("f" * 40, "x", "1+github-actions[bot]@users.noreply.github.com", "noreply@github.com", "chore: promote")]
        self.assertEqual(dco.unsigned(bots), [])


class ReadRange(unittest.TestCase):
    def test_reads_author_email_and_message_of_each_non_merge_commit(self):
        with tempfile.TemporaryDirectory() as d:
            def run(*args, cwd=d):
                subprocess.run(args, cwd=cwd, check=True, capture_output=True)

            run("git", "init", "-q", "-b", "main")
            run("git", "config", "user.name", "Ana Dev")
            run("git", "config", "user.email", "ana@example.org")
            run("git", "commit", "-q", "--allow-empty", "-m", "base")
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, check=True, capture_output=True, text=True).stdout.strip()
            run("git", "commit", "-q", "--allow-empty", "-s", "-m", "feat: signed")
            run("git", "commit", "-q", "--allow-empty", "-m", "feat: unsigned")
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, check=True, capture_output=True, text=True).stdout.strip()
            cwd = os.getcwd()
            os.chdir(d)
            try:
                commits = dco.read_range(base, head)
            finally:
                os.chdir(cwd)
            self.assertEqual([c[4].splitlines()[0] for c in commits], ["feat: unsigned", "feat: signed"])
            self.assertEqual(len(dco.unsigned(commits)), 1)


if __name__ == "__main__":
    unittest.main()
