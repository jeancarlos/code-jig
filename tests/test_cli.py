import contextlib
import io
import subprocess
import unittest
from pathlib import Path

from codejig import VERSION
from codejig.__main__ import build_parser

ROOT = Path(__file__).resolve().parent.parent
OLD_NAMES = ("codex-" "harness", "codex" "harness", "CODEX_" "HARNESS_", "-m " "harness", "from " "harness")
OLD_NAMES_ALLOWED = ("docs/", "README.md", "CONTRIBUTING.md", "tests/fixtures/", "codejig/migrate.py",
                     "tests/test_migrate.py", "tests/test_golden.py")


class Cli(unittest.TestCase):
    def test_version_is_semver(self):
        self.assertRegex(VERSION, r"^\d+\.\d+\.\d+$")

    def test_doctor_flags_parse(self):
        a = build_parser().parse_args(["--overlay", "x", "doctor", "--codex-bin", "y", "--check-binary"])
        self.assertEqual((a.cmd, a.overlay, a.codex_bin, a.check_binary), ("doctor", "x", "y", True))

    def test_command_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args([])

    def test_no_old_names_outside_migrate(self):
        files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
        hits = []
        for rel in files.decode("utf-8").split("\0"):
            path = ROOT / rel
            if not rel or rel.startswith(OLD_NAMES_ALLOWED) or not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", "ignore")
            hits += [f"{rel}: {name}" for name in OLD_NAMES if name in text]
        self.assertEqual(hits, [])
