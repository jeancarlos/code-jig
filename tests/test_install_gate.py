import os
import subprocess
import unittest
from unittest import mock

from codejig import install, paths
from codejig.doctor import check_git_gate
from codejig.overlay import Overlay
from tests.util import tree, write


def global_hooks(env: dict) -> str:
    return subprocess.run(["git", "config", "--global", "--get", "core.hooksPath"], capture_output=True, text=True,
                          encoding="utf-8", env=env).stdout.strip()


class Gate(unittest.TestCase):
    def setUp(self):
        root = tree(self)
        self.home = root / "codex home"
        self.gitconfig = root / "gitconfig"
        self.env = {**os.environ, "GIT_CONFIG_GLOBAL": str(self.gitconfig), "GIT_CONFIG_NOSYSTEM": "1"}
        patcher = mock.patch.dict(os.environ, self.env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.on = Overlay(root / "ov", "v1", True, git_gate=True, prose_gate=True)
        self.off = Overlay(root / "ov", "v1", True)
        self.target = paths.state_dir() / "git-hooks"

    def test_enables_when_unset_and_doctor_agrees(self):
        lines = install.git_gate(self.on)
        self.assertEqual(global_hooks(self.env), str(self.target))
        self.assertTrue((self.target / "pre-commit").is_file())
        self.assertIn("--prose", (self.target / "pre-commit").read_text(encoding="utf-8"))
        self.assertTrue(any("core.hooksPath" in line for line in lines))
        [(level, _, _)] = check_git_gate(self.on, self.home)
        self.assertEqual(level, "ok")

    def test_never_replaces_someone_elses_hooks_path(self):
        write(self.gitconfig, "[core]\n\thooksPath = /elsewhere\n")
        lines = install.git_gate(self.on)
        self.assertEqual(global_hooks(self.env), "/elsewhere")
        self.assertTrue(any(line.startswith("warning") and "/elsewhere" in line for line in lines))
        [(level, _, detail)] = check_git_gate(self.on, self.home)
        self.assertEqual(level, "warn")
        self.assertIn("/elsewhere", detail)

    def test_turning_it_off_unsets_only_ours(self):
        install.git_gate(self.on)
        install.git_gate(self.off)
        self.assertEqual(global_hooks(self.env), "")
        write(self.gitconfig, "[core]\n\thooksPath = /elsewhere\n")
        install.git_gate(self.off)
        self.assertEqual(global_hooks(self.env), "/elsewhere")

    def test_off_and_unset_is_silent(self):
        self.assertEqual(install.git_gate(self.off), [])
        self.assertEqual(check_git_gate(self.off, self.home), [("ok", "git gate", "off")])

    def test_repo_override_warns(self):
        install.git_gate(self.on)
        repo = tree(self)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", ".husky"], check=True)
        [(level, _, detail)] = check_git_gate(self.on, repo)
        self.assertEqual(level, "warn")
        self.assertIn(".husky", detail)


if __name__ == "__main__":
    unittest.main()
