import subprocess
import unittest
from unittest import mock

import bootstrap
from tests.util import tree, write


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def overlay(root, pin="v0.11.0", own=False):
    head = bootstrap.OWN + "\n" if own else ""
    write(root / "overlay.toml", f'{head}core_version = "{pin}"\ncore_writable = false\n')
    return root


class Classify(unittest.TestCase):
    def test_git_forms(self):
        for url in ("https://github.com/o/r.git", "ssh://git@host/o/r", "git@github.com:o/r.git"):
            with self.subTest(url=url):
                self.assertEqual(bootstrap.classify(url), "git")

    def test_paths(self):
        for p in ("~/code-jig-overlay", "/srv/ov", "C:\\Users\\João\\ov", "rel/ov"):
            with self.subTest(p=p):
                self.assertEqual(bootstrap.classify(p), "path")

    def test_refused(self):
        for bad in ("--upload-pack=touch /tmp/x", "-c", "ext::sh -c touch% /tmp/x", "file:///srv/ov",
                    "http://h/o/r", "https://user:tok@github.com/o/r", "https://tok@github.com/o/r",
                    "ssh://u:pw@host/r", "fd::17"):
            with self.subTest(bad=bad), self.assertRaises(bootstrap.Refused):
                bootstrap.classify(bad)

    def test_refusal_never_echoes_the_value(self):
        for bad in ("http://alice:ghp_SECRET@github.com/o/r", "ext::sh -c ghp_SECRET", "--ghp_SECRET"):
            with self.subTest(bad=bad), self.assertRaises(bootstrap.Refused) as ctx:
                bootstrap.classify(bad)
            self.assertNotIn("ghp_SECRET", str(ctx.exception))


class Clone(unittest.TestCase):
    def setUp(self):
        root = tree(self)
        self.origin = root / "origin"
        overlay(self.origin)
        git(self.origin, "init", "-q")
        git(self.origin, "add", "-A")
        git(self.origin, "commit", "-q", "-m", "c")
        self.dest = root / "dest"

    def run_clone(self, url):
        with mock.patch.object(bootstrap, "CLONE_CONFIG", ["-c", "protocol.ext.allow=never"]):
            bootstrap.clone(url, self.dest)

    def test_clone_then_pull(self):
        url = str(self.origin)
        self.run_clone(url)
        self.assertTrue((self.dest / "overlay.toml").is_file())
        write(self.origin / "overlay.toml", 'core_version = "v0.12.0"\ncore_writable = false\n')
        git(self.origin, "commit", "-q", "-am", "bump")
        self.run_clone(url)
        self.assertEqual(bootstrap.read_pin(self.dest), "v0.12.0")

    def test_insteadof_rewrite_does_not_break_rerun(self):
        url = str(self.origin)
        self.run_clone(url)
        git(self.dest, "config", f"url.{url}/.insteadOf", url)
        self.run_clone(url)

    def test_other_origin_refused(self):
        self.run_clone(str(self.origin))
        with self.assertRaises(bootstrap.Refused):
            bootstrap.clone("https://github.com/someone/else.git", self.dest)

    def test_clone_config_blocks_ext_and_file(self):
        self.assertEqual(bootstrap.CLONE_CONFIG,
                         ["-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=never"])

    def test_existing_non_clone_refused(self):
        self.dest.mkdir()
        with self.assertRaises(bootstrap.Refused):
            bootstrap.clone("https://github.com/o/r.git", self.dest)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.dest = self.root / "code-jig-overlay"

    def test_path_needs_overlay_toml(self):
        with self.assertRaises(bootstrap.Refused):
            bootstrap.resolve_overlay(str(self.root / "nothing"), self.dest)
        ov = overlay(self.root / "mine")
        self.assertEqual(bootstrap.resolve_overlay(str(ov), self.dest), ov)

    def test_default_dir_reused_or_created_later(self):
        self.assertIsNone(bootstrap.resolve_overlay(None, self.dest))
        overlay(self.dest)
        self.assertEqual(bootstrap.resolve_overlay(None, self.dest), self.dest)

    def test_default_dir_without_overlay_toml_refused(self):
        write(self.dest / "notes.txt", "mine")
        with self.assertRaises(bootstrap.Refused):
            bootstrap.resolve_overlay(None, self.dest)

    def test_git_url_clones_into_dest(self):
        with mock.patch.object(bootstrap, "clone", side_effect=lambda url, dest: overlay(dest)) as c:
            self.assertEqual(bootstrap.resolve_overlay("git@github.com:o/r.git", self.dest), self.dest)
        c.assert_called_once_with("git@github.com:o/r.git", self.dest)


class Pins(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def test_read_pin_validates(self):
        self.assertEqual(bootstrap.read_pin(overlay(self.root / "a")), "v0.11.0")
        with self.assertRaises(bootstrap.Refused):
            bootstrap.read_pin(overlay(self.root / "b", pin="main"))

    def test_git_overlay_is_never_owned(self):
        ov = overlay(self.root / "g", own=True)
        self.assertTrue(bootstrap.owned(ov))
        git(ov, "init", "-q")
        self.assertFalse(bootstrap.owned(ov))
        with mock.patch.object(bootstrap, "resolve_latest", return_value="v0.13.0"):
            with self.assertRaisesRegex(bootstrap.Refused, "bump core_version"):
                bootstrap.choose_tag("v0.12.0", ov, "o/r")

    def test_create_overlay_writes_own_marker_and_pin(self):
        core = self.root / "core"
        write(core / "overlay-examples" / "release" / "overlay.toml", 'core_version = "v0.0.1"\ncore_writable = false\n')
        write(core / "overlay-examples" / "release" / "profiles.toml", 'default = "m"\n')
        ov = bootstrap.create_overlay(core, self.root / "ov", "v0.11.0")
        self.assertTrue(bootstrap.owned(ov))
        self.assertEqual(bootstrap.read_pin(ov), "v0.11.0")
        self.assertTrue((ov / "profiles.toml").is_file())
        bootstrap.write_pin(ov, "v0.12.0")
        self.assertEqual(bootstrap.read_pin(ov), "v0.12.0")
        self.assertTrue(bootstrap.owned(ov))


class ChooseTag(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.latest = mock.patch.object(bootstrap, "resolve_latest", return_value="v0.13.0")
        self.latest.start()
        self.addCleanup(self.latest.stop)

    def test_no_overlay(self):
        self.assertEqual(bootstrap.choose_tag(None, None, "o/r"), "v0.13.0")
        self.assertEqual(bootstrap.choose_tag("v0.11.0", None, "o/r"), "v0.11.0")

    def test_pin_wins_without_flag(self):
        self.assertEqual(bootstrap.choose_tag(None, overlay(self.root / "a"), "o/r"), "v0.11.0")

    def test_foreign_overlay_refuses_a_different_version(self):
        ov = overlay(self.root / "a")
        self.assertEqual(bootstrap.choose_tag("v0.11.0", ov, "o/r"), "v0.11.0")
        for v in ("v0.12.0", "latest"):
            with self.subTest(v=v), self.assertRaisesRegex(bootstrap.Refused, "bump core_version"):
                bootstrap.choose_tag(v, ov, "o/r")

    def test_owned_overlay_accepts_a_new_version(self):
        ov = overlay(self.root / "a", own=True)
        self.assertEqual(bootstrap.choose_tag("latest", ov, "o/r"), "v0.13.0")
        self.assertEqual(bootstrap.choose_tag("v0.10.9", ov, "o/r"), "v0.10.9")

    def test_bad_version_refused(self):
        with self.assertRaises(bootstrap.Refused):
            bootstrap.choose_tag("v1", None, "o/r")
