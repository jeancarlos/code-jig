import subprocess
import unittest
from unittest import mock

from harness.doctor import check_core
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
