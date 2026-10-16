import contextlib
import io
import sqlite3
import types
import unittest
from unittest import mock

from codejig import collect
from codejig.__main__ import build_parser
from tests.util import tree


class Cli(unittest.TestCase):
    def run_cli(self, home, rescan=False):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = collect.cli(types.SimpleNamespace(codex_home=str(home), rescan=rescan))
        return code, out.getvalue(), err.getvalue()

    def test_prints_empty_json_and_summary_on_stderr(self):
        home = tree(self) / "codex home"
        code, out, err = self.run_cli(home)
        self.assertEqual((code, out), (0, "{}\n"))
        self.assertIn("files", err)

    def test_failure_still_prints_json_and_exits_0(self):
        home = tree(self) / "codex home"
        with mock.patch.object(collect, "connect", side_effect=sqlite3.OperationalError("database is locked")):
            code, out, err = self.run_cli(home)
        self.assertEqual((code, out), (0, "{}\n"))
        self.assertIn("database is locked", err)

    def test_parser_has_collect(self):
        args = build_parser().parse_args(["collect", "--rescan"])
        self.assertEqual((args.cmd, args.rescan), ("collect", True))
