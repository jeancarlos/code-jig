import contextlib
import io
import unittest

from harness import VERSION
from harness.__main__ import build_parser


class Cli(unittest.TestCase):
    def test_version_is_semver(self):
        self.assertRegex(VERSION, r"^\d+\.\d+\.\d+$")

    def test_doctor_flags_parse(self):
        a = build_parser().parse_args(["--overlay", "x", "doctor", "--codex-bin", "y", "--check-binary"])
        self.assertEqual((a.cmd, a.overlay, a.codex_bin, a.check_binary), ("doctor", "x", "y", True))

    def test_command_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args([])
