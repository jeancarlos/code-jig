import contextlib
import errno
import io
import ntpath
import os
import sqlite3
import subprocess
import types
import unittest
from pathlib import Path
from unittest import mock

from codejig import __main__, collect, install, migrate, paths
from codejig.overlay import Overlay
from tests.util import tree, write


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", cwd=cwd)


def values(key: str, repo: Path | None = None) -> list[str]:
    scope = ["-C", str(repo), "config", "--local"] if repo else ["config", "--global"]
    return git(*scope, "--get-all", key).stdout.splitlines()


def db_with_rows(path: Path, n: int) -> Path:
    with contextlib.closing(collect.connect(path)) as con:
        for i in range(n):
            con.execute("INSERT INTO threads (id, kind) VALUES (?, 'main')", (f"t{i}",))
        con.commit()
    return path


def thread_ids(path: Path) -> list[str]:
    with contextlib.closing(sqlite3.connect(path)) as con:
        return [r[0] for r in con.execute("SELECT id FROM threads ORDER BY id")]


class Migrate(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.home = self.root / "codex home"
        self.gitconfig = self.root / "gitconfig"
        patcher = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(self.gitconfig), "GIT_CONFIG_NOSYSTEM": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ov = Overlay(self.root / "ov", "v1", True)
        self.old_db = migrate.old_state(self.home) / "usage.sqlite3"

    def repo(self, name: str = "repo") -> Path:
        path = self.root / name
        path.mkdir()
        git("init", "-q", str(path))
        return path

    def run_migrate(self, repos=(), dry_run=False) -> list[str]:
        return migrate.run(paths.CORE, self.ov, self.home, list(repos), dry_run)

    def test_db_moves_to_the_state_dir(self):
        db_with_rows(self.old_db, 2)
        lines = self.run_migrate()
        self.assertFalse(self.old_db.exists())
        self.assertEqual(thread_ids(collect.db_path()), ["t0", "t1"])
        self.assertTrue(any(str(collect.db_path()) in line for line in lines))

    def test_a_populated_new_db_is_never_overwritten(self):
        db_with_rows(self.old_db, 2)
        db_with_rows(collect.db_path(), 1)
        lines = self.run_migrate()
        self.assertEqual(thread_ids(self.old_db), ["t0", "t1"])
        self.assertEqual(thread_ids(collect.db_path()), ["t0"])
        self.assertIn(f"refused: {collect.db_path()} already has data; move one of them away and rerun", lines)

    def test_an_empty_new_db_is_replaced(self):
        db_with_rows(self.old_db, 2)
        db_with_rows(collect.db_path(), 0)
        self.run_migrate()
        self.assertFalse(self.old_db.exists())
        self.assertEqual(thread_ids(collect.db_path()), ["t0", "t1"])

    def test_every_email_and_allow_prose_value_moves_and_old_keys_go(self):
        git("config", "--global", "--add", "codexharness.email", "a@example.com")
        git("config", "--global", "--add", "codexharness.email", "b@example.com")
        git("config", "--global", "--add", "codejig.email", "b@example.com")
        git("config", "--global", "codexharness.allowProse", "true")
        self.run_migrate()
        self.assertEqual(values("codejig.email"), ["b@example.com", "a@example.com"])
        self.assertEqual(values("codejig.allowProse"), ["true"])
        self.assertEqual(values("codexharness.email"), [])
        self.assertEqual(values("codexharness.allowProse"), [])

    def test_repo_args_move_their_local_allow_prose(self):
        repo = self.repo()
        git("-C", str(repo), "config", "--local", "codexharness.allowProse", "true")
        plain = self.root / "plain dir"
        plain.mkdir()
        lines = self.run_migrate([repo, plain])
        self.assertEqual(values("codejig.allowProse", repo), ["true"])
        self.assertEqual(values("codexharness.allowProse", repo), [])
        self.assertEqual(values("codejig.allowProse"), [])
        self.assertIn(f"skip {plain}: not a git repo", lines)

    def test_old_hooks_path_is_released_even_with_backslashes_and_case(self):
        home = Path("C:\\Users\\Jean\\.codex")
        git("config", "--global", "core.hooksPath", "c:\\USERS\\jean\\.CODEX\\Codex-Harness\\git-hooks")
        with mock.patch.object(install, "os", types.SimpleNamespace(path=ntpath)):
            lines = migrate.release_hooks_path(home)
        self.assertEqual(git("config", "--global", "--get", "core.hooksPath").stdout, "")
        self.assertTrue(any("core.hooksPath" in line for line in lines))

    def test_a_foreign_hooks_path_stays(self):
        git("config", "--global", "core.hooksPath", "/elsewhere")
        self.assertEqual(migrate.release_hooks_path(self.home), [])
        self.assertEqual(git("config", "--global", "--get", "core.hooksPath").stdout.strip(), "/elsewhere")

    def test_dry_run_changes_nothing(self):
        db_with_rows(self.old_db, 1)
        repo = self.repo()
        git("-C", str(repo), "config", "--local", "codexharness.allowProse", "true")
        git("config", "--global", "codexharness.email", "a@example.com")
        git("config", "--global", "core.hooksPath", str(migrate.old_state(self.home) / "git-hooks"))
        before = self.gitconfig.read_bytes()
        repo_before = (repo / ".git" / "config").read_bytes()
        lines = self.run_migrate([repo], dry_run=True)
        self.assertEqual((repo / ".git" / "config").read_bytes(), repo_before)
        self.assertTrue(self.old_db.exists())
        self.assertFalse(collect.db_path().exists())
        self.assertEqual(self.gitconfig.read_bytes(), before)
        self.assertEqual(values("codexharness.allowProse", repo), ["true"])
        self.assertEqual(len(lines), 6)
        self.assertTrue(all(line.startswith("would ") for line in lines), lines)

    def test_deprecation_notice_is_the_first_line(self):
        write(self.root / "ov" / "overlay.toml", 'core_version = "v1"\ncore_writable = true\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = __main__.main(["--overlay", str(self.root / "ov"), "--codex-home", str(self.home),
                                  "migrate", "--dry-run", str(self.repo())])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().splitlines()[0],
                         "code-jig migrate is deprecated and will be removed in the next release")

    def main(self, *args: str) -> tuple[int, list[str]]:
        write(self.root / "ov" / "overlay.toml", 'core_version = "v1"\ncore_writable = true\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = __main__.main(["--overlay", str(self.root / "ov"), "--codex-home", str(self.home), "migrate", *args])
        return code, out.getvalue().splitlines()

    def test_a_locked_git_config_keeps_the_old_key_and_exits_1(self):
        git("config", "--global", "codexharness.email", "a@example.com")
        write(self.root / "gitconfig.lock", "")
        code, lines = self.main(str(self.repo()))
        self.assertEqual(code, 1)
        self.assertEqual(values("codexharness.email"), ["a@example.com"])
        self.assertEqual(values("codejig.email"), [])
        self.assertTrue(any(line.startswith("failed:") for line in lines), lines)
        self.assertFalse(any(line.startswith("unset") for line in lines), lines)

    def test_a_cross_device_move_copies_then_removes_the_old_db(self):
        db_with_rows(self.old_db, 2)
        real = os.replace
        calls = []

        def replace(src, dst):
            calls.append(src)
            if len(calls) == 1:
                raise OSError(errno.EXDEV, "cross-device link")
            return real(src, dst)

        with mock.patch("os.replace", replace):
            lines = self.run_migrate()
        self.assertEqual(len(calls), 2)
        self.assertEqual(Path(calls[1]).parent, collect.db_path().parent)
        self.assertFalse(self.old_db.exists())
        self.assertEqual(thread_ids(collect.db_path()), ["t0", "t1"])
        self.assertEqual(sorted(p.name for p in collect.db_path().parent.iterdir()), ["usage.sqlite3"])
        self.assertFalse(any(line.startswith("refused") for line in lines), lines)

    def test_a_cross_device_move_whose_old_db_cannot_go_keeps_only_the_old_db(self):
        db_with_rows(self.old_db, 2)
        real_replace, real_unlink = os.replace, Path.unlink
        calls = []

        def replace(src, dst):
            calls.append(src)
            if len(calls) == 1:
                raise OSError(errno.EXDEV, "cross-device link")
            return real_replace(src, dst)

        def unlink(path, missing_ok=False):
            if path == self.old_db:
                raise PermissionError(errno.EACCES, "in use")
            return real_unlink(path, missing_ok)

        with mock.patch("os.replace", replace), mock.patch.object(Path, "unlink", unlink):
            lines = self.run_migrate()
        self.assertEqual(thread_ids(self.old_db), ["t0", "t1"])
        self.assertFalse(collect.db_path().exists())
        self.assertIn(f"refused: {self.old_db} is in use; close Codex and Claude Code and rerun", lines)

    def test_an_old_db_in_use_is_refused_without_copying(self):
        db_with_rows(self.old_db, 2)
        with mock.patch("os.replace", side_effect=PermissionError(errno.EACCES, "in use")):
            lines = self.run_migrate()
        self.assertEqual(thread_ids(self.old_db), ["t0", "t1"])
        self.assertFalse(collect.db_path().exists())
        self.assertIn(f"refused: {self.old_db} is in use; close Codex and Claude Code and rerun", lines)

    def test_an_old_db_with_a_hot_journal_is_refused(self):
        db_with_rows(self.old_db, 1)
        write(self.old_db.with_name("usage.sqlite3-journal"), "x")
        lines = self.run_migrate()
        self.assertTrue(self.old_db.exists())
        self.assertFalse(collect.db_path().exists())
        self.assertIn(f"refused: {self.old_db} has an unfinished write; open and close Codex once and rerun", lines)

    def test_a_corrupt_new_db_counts_as_data(self):
        db_with_rows(self.old_db, 1)
        write(collect.db_path(), "not a database " * 100)
        lines = self.run_migrate()
        self.assertTrue(self.old_db.exists())
        self.assertIn(f"refused: {collect.db_path()} already has data; move one of them away and rerun", lines)

    def test_a_refusal_exits_1(self):
        write(self.root / "ov" / "overlay.toml", 'core_version = "v1"\ncore_writable = true\n')
        db_with_rows(self.old_db, 1)
        db_with_rows(collect.db_path(), 1)
        with contextlib.redirect_stdout(io.StringIO()):
            code = __main__.main(["--overlay", str(self.root / "ov"), "--codex-home", str(self.home),
                                  "migrate", str(self.repo())])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
