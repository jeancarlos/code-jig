# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import contextlib
import io
import unittest
from unittest import mock

from codejig.doctor import SHIM_MAX_BYTES, check_binary, report, resolve_codex_bin
from tests.util import tree


def fake_binary(root, keys, size=SHIM_MAX_BYTES + 10):
    path = root / "codex.exe"
    blob = b"\0".join(k.encode() for k in keys)
    path.write_bytes(blob + b"\0" * (size - len(blob)))
    return path


class CheckBinary(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_all_keys_present(self):
        b = fake_binary(self.root, ["alpha_key", "beta_key"])
        self.assertEqual([c[0] for c in check_binary(b, ("alpha_key", "beta_key"))], ["ok"])

    def test_missing_key_fails_by_name(self):
        b = fake_binary(self.root, ["alpha_key"])
        [(level, _, detail)] = check_binary(b, ("alpha_key", "beta_key"))
        self.assertEqual(level, "FAIL")
        self.assertIn("beta_key", detail)

    def test_launcher_is_not_scanned(self):
        shim = self.root / "codex.cmd"
        shim.write_text("@node codex.js %*\n", encoding="utf-8")
        [(level, _, detail)] = check_binary(shim, ("alpha_key",))
        self.assertEqual(level, "FAIL")
        self.assertIn("--codex-bin", detail)

    def test_unreadable_binary_fails_cleanly(self):
        b = fake_binary(self.root, ["alpha_key"])
        with mock.patch("builtins.open", side_effect=PermissionError(13, "Permission denied")):
            [(level, _, detail)] = check_binary(b, ("alpha_key",))
        self.assertEqual(level, "FAIL")
        self.assertIn("cannot read", detail)

    def test_not_found(self):
        [(level, _, detail)] = check_binary(None, ("alpha_key",))
        self.assertEqual(level, "FAIL")
        self.assertIn("CODEX_BIN", detail)


class Report(unittest.TestCase):
    def test_exit_code(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(report([("ok", "a", "fine"), ("warn", "b", "hmm")]), 0)
            self.assertEqual(report([("FAIL", "c", "bad")]), 1)
        self.assertIn("FAIL c: bad", out.getvalue())


class ResolveBinary(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.shim = self.root / "codex.CMD"
        self.shim.write_text("@node codex.js %*\n", encoding="utf-8")

    def native(self):
        d = self.root / "node_modules" / "@openai" / "codex" / "vendor" / "x86_64"
        d.mkdir(parents=True)
        return fake_binary(d, ["alpha_key"])

    def test_launcher_resolves_to_the_native_binary_beside_it(self):
        native = self.native()
        self.assertEqual(resolve_codex_bin(str(self.shim)), native)

    def test_launcher_without_a_native_binary_stays_a_launcher(self):
        self.assertEqual(resolve_codex_bin(str(self.shim)), self.shim)

    def test_a_native_binary_is_kept(self):
        native = fake_binary(self.root, ["alpha_key"])
        self.native()
        self.assertEqual(resolve_codex_bin(str(native)), native)

    def test_nothing_to_resolve(self):
        with mock.patch("shutil.which", return_value=None), mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(resolve_codex_bin(None))
