import hashlib
import subprocess
import unittest
from unittest import mock

from harness.doctor import check_core, check_global
from harness.install import release_digest, render_agents, stamp
from harness.overlay import Overlay
from tests.util import tree, write


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


class Core(unittest.TestCase):
    def setUp(self):
        self.core = tree(self) / "core"
        write(self.core / "f.txt", "a")
        git(self.core, "init", "-q")
        git(self.core, "add", "-A")
        git(self.core, "commit", "-q", "-m", "c")
        git(self.core, "tag", "v0.1.0")

    def levels(self, ov):
        return {name: level for level, name, _ in check_core(self.core, ov)}

    def test_pinned_clean_readonly_ok(self):
        self.assertEqual(self.levels(Overlay(self.core, "v0.1.0", False)), {"core pin": "ok", "core clean": "ok"})

    def test_dirty_readonly_fails(self):
        write(self.core / "f.txt", "changed")
        self.assertEqual(self.levels(Overlay(self.core, "v0.1.0", False))["core clean"], "FAIL")

    def test_dirty_writable_is_fine(self):
        write(self.core / "f.txt", "changed")
        self.assertEqual(self.levels(Overlay(self.core, "v0.1.0", True))["core clean"], "ok")

    def test_wrong_pin_readonly_fails_writable_warns(self):
        self.assertEqual(self.levels(Overlay(self.core, "v9.9.9", False))["core pin"], "FAIL")
        self.assertEqual(self.levels(Overlay(self.core, "v9.9.9", True))["core pin"], "warn")


class NotGit(unittest.TestCase):
    def setUp(self):
        self.core = tree(self) / "core"
        write(self.core / "f.txt", "a")

    def test_non_git_core_fails_clean_both_modes(self):
        for writable in (False, True):
            levels = {name: level for level, name, _ in check_core(self.core, Overlay(self.core, "v0.1.0", writable))}
            self.assertEqual(levels["core clean"], "FAIL")

    def test_missing_git_fails_without_crashing(self):
        with mock.patch("harness.doctor.subprocess.run", side_effect=FileNotFoundError("git")):
            checks = check_core(self.core, Overlay(self.core, "v0.1.0", False))
        self.assertEqual({name: level for level, name, _ in checks}["core clean"], "FAIL")


class GitFailure(unittest.TestCase):
    def setUp(self):
        self.core = tree(self) / "core"
        write(self.core / "f.txt", "a")

    def test_stderr_in_detail_and_pin_not_untagged(self):
        fail = mock.Mock(returncode=128, stdout="", stderr="fatal: detected dubious ownership\nmore\n")
        with mock.patch("harness.doctor.subprocess.run", return_value=fail):
            pin, clean = check_core(self.core, Overlay(self.core, "v0.1.0", False))
        self.assertIn("dubious ownership", clean[2])
        self.assertNotIn("more", clean[2])
        self.assertNotIn("untagged", pin[2])
        self.assertIn("cannot be checked", pin[2])


class GlobalAgents(unittest.TestCase):
    def setUp(self):
        root = tree(self)
        self.core = root / "core"
        write(self.core / "core" / "AGENTS.core.md", "core rules\n")
        self.ovdir = root / "ov"
        self.ovdir.mkdir()
        self.ov = Overlay(self.ovdir, "v0.1.0", True)
        self.home = root / "home"
        self.home.mkdir()

    def level(self):
        [(level, name, _)] = check_global(self.home, self.core, self.ov)
        self.assertEqual(name, "global AGENTS.md")
        return level

    def test_ok(self):
        write(self.home / "AGENTS.md", render_agents(self.core, self.ovdir))
        self.assertEqual(self.level(), "ok")

    def test_missing_warns(self):
        self.assertEqual(self.level(), "warn")

    def test_stale_warns(self):
        write(self.home / "AGENTS.md", stamp("old\n"))
        self.assertEqual(self.level(), "warn")

    def test_override_fails(self):
        write(self.home / "AGENTS.md", render_agents(self.core, self.ovdir))
        write(self.home / "AGENTS.override.md", "x\n")
        self.assertEqual(self.level(), "FAIL")

    def test_empty_override_ignored(self):
        write(self.home / "AGENTS.md", render_agents(self.core, self.ovdir))
        write(self.home / "AGENTS.override.md", "")
        self.assertEqual(self.level(), "ok")


class Release(unittest.TestCase):
    def setUp(self):
        self.core = tree(self) / "core"
        write(self.core / "harness" / "x.py", "a\n")
        write(self.core / "VERSION", f"v0.1.0\n{release_digest(self.core)}\n")

    def levels(self, ov):
        return {name: level for level, name, _ in check_core(self.core, ov)}

    def test_matching_release_is_ok(self):
        self.assertEqual(self.levels(Overlay(self.core, "v0.1.0", False)), {"core pin": "ok", "core clean": "ok"})

    def test_edited_release_fails_readonly_ok_writable(self):
        write(self.core / "harness" / "x.py", "b\n")
        self.assertEqual(self.levels(Overlay(self.core, "v0.1.0", False))["core clean"], "FAIL")
        self.assertEqual(self.levels(Overlay(self.core, "v0.1.0", True))["core clean"], "ok")

    def test_wrong_pin_readonly_fails_writable_warns(self):
        self.assertEqual(self.levels(Overlay(self.core, "v9.9.9", False))["core pin"], "FAIL")
        self.assertEqual(self.levels(Overlay(self.core, "v9.9.9", True))["core pin"], "warn")

    def test_pycache_and_version_are_not_digested(self):
        write(self.core / "harness" / "__pycache__" / "x.cpython-313.pyc", "bytecode")
        self.assertEqual(self.levels(Overlay(self.core, "v0.1.0", False)), {"core pin": "ok", "core clean": "ok"})

    def test_parent_git_repo_does_not_count(self):
        git(self.core.parent, "init", "-q")
        self.assertEqual(self.levels(Overlay(self.core, "v0.1.0", False)), {"core pin": "ok", "core clean": "ok"})

    def test_unreadable_version_fails(self):
        with mock.patch("pathlib.Path.read_text", side_effect=PermissionError("denied")):
            out = check_core(self.core, Overlay(self.core, "v0.1.0", False))
        self.assertEqual(out[0][0], "FAIL")
        self.assertIn("cannot read VERSION", out[0][2])

    def test_garbled_version_file_fails_readonly(self):
        write(self.core / "VERSION", "nonsense")
        levels = self.levels(Overlay(self.core, "v0.1.0", False))
        self.assertEqual((levels["core pin"], levels["core clean"]), ("FAIL", "FAIL"))


class ReleaseDigest(unittest.TestCase):
    def test_order_is_by_posix_string(self):
        root = tree(self)
        write(root / "a-b" / "x", "1")
        write(root / "a" / "b", "2")
        h = hashlib.sha256()
        for rel in sorted(["a-b/x", "a/b"]):
            h.update(rel.encode() + b"\0" + (root / rel).read_bytes() + b"\0")
        self.assertEqual(release_digest(root), h.hexdigest())
