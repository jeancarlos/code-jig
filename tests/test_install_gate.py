import os
import subprocess
import unittest
from unittest import mock

from codejig import gitgate, install, paths
from codejig.doctor import check_git_gate
from codejig.overlay import Overlay, load
from tests.test_gitgate import in_repo
from tests.test_scrub import CODEX, ME, commit, git, new_repo
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

    def overlay(self, extra: str) -> Overlay:
        root = tree(self)
        write(root / "overlay.toml", f'core_version = "v1"\ncore_writable = true\n{extra}')
        return load(root)

    def pre_push_shim(self, ov: Overlay) -> str:
        install.git_gate(ov)
        return (self.target / "pre-push").read_text(encoding="utf-8")

    def test_push_cleanup_defaults_on_with_the_gate(self):
        self.assertIsNone(self.overlay("").push_cleanup)
        self.assertEqual(install.git_gate(self.overlay("")), [])
        on = self.overlay("git_gate = true\n")
        self.assertIsNone(on.push_cleanup)
        self.assertIn("git-hook --cleanup pre-push", self.pre_push_shim(on))
        self.assertTrue(self.overlay("git_gate = true\npush_cleanup = true\n").push_cleanup)
        with self.assertRaisesRegex(ValueError, "push_cleanup must be true or false"):
            self.overlay('push_cleanup = "yes"\n')

    def test_push_cleanup_false_in_overlay_or_git_config_turns_it_off(self):
        off = self.overlay("git_gate = true\npush_cleanup = false\n")
        self.assertIs(off.push_cleanup, False)
        self.assertNotIn("--cleanup", self.pre_push_shim(off))
        repo = new_repo(self)
        base = commit(repo, "init\n", ME, {"a": "1\n"}, 1_700_000_000)
        tip = commit(repo, f"mine\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        git(repo, "config", "codejig.pushCleanup", "false")
        code, err = in_repo(repo, gitgate.pre_push, [f"refs/heads/main {tip} refs/heads/main {base}"], True)
        self.assertEqual(code, 1)
        self.assertIn("code-jig scrub", err)
        self.assertEqual(git(repo, "rev-parse", "main"), tip)

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
