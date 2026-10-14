import os
import unittest
from unittest import mock

from harness import paths
from harness.overlay import load
from tests.util import tree, write


class LoadOverlay(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_reads_fields(self):
        write(self.root / "overlay.toml", 'core_version = "v0.1.0"\ncore_writable = false\n')
        o = load(self.root)
        self.assertEqual((o.root, o.core_version, o.core_writable), (self.root, "v0.1.0", False))

    def test_missing_key_named(self):
        write(self.root / "overlay.toml", 'core_version = "v0.1.0"\n')
        with self.assertRaisesRegex(ValueError, "core_writable"):
            load(self.root)

    def test_non_bool_writable(self):
        write(self.root / "overlay.toml", 'core_version = "v0.1.0"\ncore_writable = "no"\n')
        with self.assertRaisesRegex(ValueError, "true or false"):
            load(self.root)

    def test_malformed_toml_names_file(self):
        write(self.root / "overlay.toml", "core_version = \n")
        with self.assertRaisesRegex(ValueError, "overlay.toml"):
            load(self.root)


class Encodings(unittest.TestCase):
    def test_bom_toml_loads(self):
        root = tree(self)
        (root / "overlay.toml").write_bytes(b"\xef\xbb\xbf" + b'core_version = "v0.1.0"\ncore_writable = true\n')
        self.assertEqual(load(root).core_version, "v0.1.0")

    def test_utf16_toml_names_file(self):
        root = tree(self)
        (root / "overlay.toml").write_bytes('core_version = "v0.1.0"\n'.encode("utf-16"))
        with self.assertRaisesRegex(ValueError, "overlay.toml"):
            load(root)


class OverlayDir(unittest.TestCase):
    def test_unset_exits_with_hint(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, "CODEX_HARNESS_OVERLAY"):
                paths.overlay_dir(None)

    def test_missing_toml_exits(self):
        root = tree(self)
        with self.assertRaisesRegex(SystemExit, "overlay.toml"):
            paths.overlay_dir(str(root))

    def test_env_used(self):
        root = tree(self)
        write(root / "overlay.toml", 'core_version = "v0.1.0"\ncore_writable = true\n')
        with mock.patch.dict(os.environ, {"CODEX_HARNESS_OVERLAY": str(root)}):
            self.assertEqual(paths.overlay_dir(None), root)

    def test_codex_home_precedence(self):
        with mock.patch.dict(os.environ, {"CODEX_HOME": "/env/home"}):
            self.assertEqual(str(paths.codex_home("/arg/home")), str(paths.Path("/arg/home")))
            self.assertEqual(str(paths.codex_home(None)), str(paths.Path("/env/home")))


if __name__ == "__main__":
    unittest.main()
