import os
import unittest
from pathlib import Path
from unittest import mock

from codejig import paths, tiers
from codejig.overlay import load
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

    def test_compact_limit_defaults_to_none(self):
        write(self.root / "overlay.toml", 'core_version = "v0.1.0"\ncore_writable = true\n')
        self.assertIsNone(load(self.root).auto_compact_token_limit)

    def test_compact_limit_read(self):
        write(self.root / "overlay.toml", 'core_version = "v0.1.0"\ncore_writable = true\nauto_compact_token_limit = 150000\n')
        self.assertEqual(load(self.root).auto_compact_token_limit, 150000)

    def test_compact_limit_must_be_a_positive_integer(self):
        for bad in ("0", "-5", '"150000"', "true", "1.5"):
            write(self.root / "overlay.toml", f'core_version = "v0.1.0"\ncore_writable = true\nauto_compact_token_limit = {bad}\n')
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "auto_compact_token_limit must be a positive integer"):
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
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(SystemExit, "CODE_JIG_OVERLAY"):
            paths.overlay_dir(None)

    def test_missing_toml_exits(self):
        root = tree(self)
        with self.assertRaisesRegex(SystemExit, "overlay.toml"):
            paths.overlay_dir(str(root))

    def test_env_used(self):
        root = tree(self)
        write(root / "overlay.toml", 'core_version = "v0.1.0"\ncore_writable = true\n')
        with mock.patch.dict(os.environ, {"CODE_JIG_OVERLAY": str(root)}):
            self.assertEqual(paths.overlay_dir(None), root)

    def test_codex_home_precedence(self):
        with mock.patch.dict(os.environ, {"CODEX_HOME": "/env/home"}):
            self.assertEqual(str(paths.codex_home("/arg/home")), str(paths.Path("/arg/home")))
            self.assertEqual(str(paths.codex_home(None)), str(paths.Path("/env/home")))


if __name__ == "__main__":
    unittest.main()


class Resolve(unittest.TestCase):
    def test_relative_overlay_becomes_absolute(self):
        import os

        from codejig import paths
        root = tree(self)
        write(root / "ov" / "overlay.toml", 'core_version = "v1"\ncore_writable = true\n')
        old = os.getcwd()
        os.chdir(root)
        self.addCleanup(os.chdir, old)
        self.assertTrue(paths.overlay_dir("ov").is_absolute())


class ReleaseExample(unittest.TestCase):
    def test_release_example_is_readonly_and_loads(self):
        root = Path(__file__).resolve().parent.parent
        ov = load(root / "overlay-examples" / "release")
        self.assertFalse(ov.core_writable)
        self.assertRegex(ov.core_version, r"^v\d+\.\d+\.\d+$")
        self.assertTrue(tiers.load(root, ov.root))
        text = (root / "overlay-examples" / "release" / "AGENTS.overlay.md").read_text(encoding="utf-8")
        self.assertNotIn("bench", text.lower())
