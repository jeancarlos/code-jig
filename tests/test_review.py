import subprocess
import sys
import types
import unittest
from unittest import mock

from harness import probe, review
from tests.util import tree, write


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class Gather(unittest.TestCase):
    def setUp(self):
        self.repo = tree(self) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "init")

    def test_working_tree_diff(self):
        write(self.repo / "a.py", "x = 1\n")
        git(self.repo, "add", "a.py")
        self.assertIn("+x = 1", review.gather(self.repo, None, []))

    def test_no_changes(self):
        with self.assertRaisesRegex(ValueError, "nothing to review"):
            review.gather(self.repo, None, [])

    def test_files(self):
        write(self.repo / "doc.md", "plan\n")
        self.assertIn("plan", review.gather(self.repo, None, ["doc.md"]))

    def test_binary_file(self):
        (self.repo / "b.bin").write_bytes(b"\x00\xff\x00")
        with self.assertRaisesRegex(ValueError, "b.bin"):
            review.gather(self.repo, None, ["b.bin"])

    def test_over_cap(self):
        write(self.repo / "big.md", "x" * (review.MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "200000"):
            review.gather(self.repo, None, ["big.md"])

    def test_outside_git_without_files(self):
        with self.assertRaisesRegex(ValueError, "git"):
            review.gather(tree(self), None, [])


class Cli(unittest.TestCase):
    def test_runs_codex_read_only_and_prints_findings(self):
        root = tree(self)
        write(root / "doc.md", "plan\n")
        fake = write(root / "fake.py", "import sys\nargs = sys.argv[1:]\nopen(args[args.index('-o') + 1], 'w').write('F1 doc.md:1 bug\\n')\nsys.stdin.read()\n")
        with mock.patch.object(probe, "command", lambda b: [sys.executable, str(fake)]), \
             mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as out:
            code = review.cli(types.SimpleNamespace(base=None, profile="review", codex_bin=str(root / "codex"), files=[str(root / "doc.md")], codex_home=None))
        self.assertEqual(code, 0)
        self.assertIn("F1 doc.md:1 bug", out.getvalue())
