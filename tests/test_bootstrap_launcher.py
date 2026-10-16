import contextlib
import io
import os
import shlex
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import bootstrap
from tests.util import tree, write

ROOT = Path(__file__).resolve().parent.parent


class Launcher(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        odd = "it's 100% & ação" if os.name != "nt" else "100% & ação"
        self.core = self.root / odd / "core"
        shutil.copytree(ROOT / "codejig", self.core / "codejig", ignore=shutil.ignore_patterns("__pycache__"))
        self.overlay = self.root / odd / "overlay"
        write(self.overlay / "overlay.toml", 'core_version = "v0.11.0"\ncore_writable = false\n')
        self.bins = self.root / "bin"

    def test_foreign_launcher_refused(self):
        write(bootstrap.launcher_path(self.bins), "#!/bin/sh\nexec python3 -m codejig \"$@\"\n")
        with self.assertRaises(bootstrap.Refused):
            bootstrap.check_launcher(bootstrap.launcher_path(self.bins))

    def test_own_launcher_is_replaced(self):
        path = bootstrap.write_launcher(self.bins, sys.executable, self.core, self.overlay, "v0.11.0")
        bootstrap.check_launcher(path)
        path = bootstrap.write_launcher(self.bins, sys.executable, self.core, self.overlay, "v0.12.0")
        self.assertIn(bootstrap.MARK + "v0.12.0", path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(p.name for p in self.bins.iterdir()), [path.name])

    def round_trip(self):
        path = bootstrap.write_launcher(self.bins, sys.executable, self.core, self.overlay, "v0.11.0")
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "CODE_JIG_OVERLAY")}
        done = subprocess.run([str(path), "--help"], env=env, capture_output=True, text=True, encoding="utf-8",
                              cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("usage: code-jig", done.stdout)
        return path

    @unittest.skipIf(os.name == "nt", "sh launcher")
    def test_sh_launcher_round_trip(self):
        path = self.round_trip()
        self.assertTrue(os.access(path, os.X_OK))
        self.assertIn("-P -s -m codejig", path.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "nt", "cmd launcher")
    def test_cmd_launcher_round_trip_non_ascii(self):
        path = self.round_trip()
        self.assertTrue(path.read_bytes().count(b"\r\n") > 3)

    def test_exit_code_propagates(self):
        path = bootstrap.write_launcher(self.bins, sys.executable, self.core, self.overlay, "v0.11.0")
        done = subprocess.run([str(path), "no-such-command"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 2)

    def test_planted_module_in_cwd_is_ignored(self):
        path = bootstrap.write_launcher(self.bins, sys.executable, self.core, self.overlay, "v0.11.0")
        cwd = self.root / "hostile"
        write(cwd / "codejig" / "__init__.py", "raise SystemExit(99)\n")
        write(cwd / "codejig" / "__main__.py", "raise SystemExit(99)\n")
        done = subprocess.run([str(path), "--help"], capture_output=True, text=True, encoding="utf-8", cwd=cwd)
        self.assertEqual(done.returncode, 0, done.stderr)


class PathHint(unittest.TestCase):
    def test_windows_text_runs_once_and_escapes(self):
        text = bootstrap.hint_lines("C:\\a $b`c'd", "nt")
        self.assertIn("once", text[0])
        self.assertNotIn("shell profile", text[0])
        self.assertIn(";C:\\a $b`c''d'", text[1])
        self.assertNotIn('"', text[1])

    def test_posix_text_unchanged(self):
        text = bootstrap.hint_lines("/x y", "posix")
        self.assertIn("add this line to your shell profile", text[0])
        self.assertEqual(text[1], "export PATH='/x y':$PATH")

    def test_hint_only_when_missing(self):
        bins = tree(self)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"PATH": str(bins)}), contextlib.redirect_stdout(out):
            bootstrap.path_hint(bins)
        self.assertEqual(out.getvalue(), "")
        with mock.patch.dict(os.environ, {"PATH": ""}), contextlib.redirect_stdout(out):
            bootstrap.path_hint(bins)
        self.assertIn("not on PATH", out.getvalue())
        if os.name == "nt":
            self.assertIn("SetEnvironmentVariable", out.getvalue())
        else:
            self.assertIn(f"export PATH={shlex.quote(str(bins))}:$PATH", out.getvalue())
