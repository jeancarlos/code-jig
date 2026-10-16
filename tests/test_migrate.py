import contextlib
import errno
import hashlib
import io
import json
import ntpath
import os
import sqlite3
import subprocess
import types
import unittest
from pathlib import Path
from unittest import mock

from codejig import __main__, collect, doctor, install, migrate, paths
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
        self.user = self.root / "user home"
        self.user.mkdir()
        self.skills = self.user / ".agents" / "skills"
        patcher = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(self.gitconfig), "GIT_CONFIG_NOSYSTEM": "1",
                                               "HOME": str(self.user), "USERPROFILE": str(self.user),
                                               "CODE_JIG_SKILLS_DIR": str(self.skills)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ov = Overlay(self.root / "ov", "v1", True)
        write(self.ov.root / "profiles.toml", 'bulk = "m-a"\ndefault = "m-a"\nreview = "n-b"\ndeep = "n-b"\n')
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
        self.assertEqual(len(lines), 9)
        self.assertIn("would run code-jig install", lines)
        self.assertTrue(all(line.startswith("would ") for line in lines), lines)
        self.assertFalse((self.home / "AGENTS.md").exists())
        self.assertFalse(any(p.exists() for p in self.launchers()))

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
            lines = migrate.move_db(self.home)
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
            lines = migrate.move_db(self.home)
        self.assertEqual(thread_ids(self.old_db), ["t0", "t1"])
        self.assertFalse(collect.db_path().exists())
        self.assertIn(f"refused: {self.old_db} is in use; close Codex and Claude Code and rerun", lines)

    def test_an_old_db_in_use_is_refused_without_copying(self):
        db_with_rows(self.old_db, 2)
        with mock.patch("os.replace", side_effect=PermissionError(errno.EACCES, "in use")):
            lines = migrate.move_db(self.home)
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

    def launchers(self) -> list[Path]:
        bs = migrate._bootstrap(paths.CORE)
        return bs.launcher_paths(bs.bin_dir(None, bs.data_dir(None)))

    def bin_dir(self) -> Path:
        bs = migrate._bootstrap(paths.CORE)
        return bs.bin_dir(None, bs.data_dir(None))

    def link(self, link: Path, target: Path):
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError as e:
            self.skipTest(f"no symlinks here: {e}")

    def old_codex_state(self):
        write(self.home / "AGENTS.md", old_stamp("old rules\n"))
        write(self.home / "default.config.toml", old_stamp('model = "x"\n', "hash"))
        write(self.home / "agents" / "explorer.toml", old_stamp('model = "x"\n', "hash"))
        write(self.home / "rules" / "codex-harness-safe.rules", old_stamp("rule\n", "hash"))
        write(migrate.old_state(self.home) / "lib" / "harness" / "install.py", old_stamp("x = 1\n", "hash"))
        write(migrate.old_state(self.home) / "git-hooks" / "pre-commit", "#!/bin/sh\n")
        write(self.home / "hooks.json", json.dumps({"hooks": {
            "Stop": [old_hook("codex-harness collect"), old_hook("mine")],
            "PostToolUse": [old_hook("codex-harness watermark")]}}))

    def old_claude_state(self) -> Path:
        settings = write(self.user / ".claude" / "settings.json", json.dumps({"model": "opus", "hooks": {
            "PostToolUse": [old_hook("codex-harness watermark"), old_hook("mine")]}}))
        return settings

    def test_old_generated_files_go_and_install_leaves_no_backups(self):
        self.old_codex_state()
        self.run_migrate()
        backups = [p for p in self.root.rglob("*") if ".bak-" in p.name and not p.name.startswith("hooks.json")]
        self.assertEqual(backups, [])
        self.assertFalse((self.home / "rules" / "codex-harness-safe.rules").exists())
        self.assertFalse(migrate.old_state(self.home).exists())
        self.assertTrue(install.is_generated(self.home / "AGENTS.md"))
        self.assertTrue(install.is_generated(self.home / "default.config.toml"))
        self.assertEqual(migrate.pending(self.home), [])

    def test_hand_edited_old_file_is_left_and_reported(self):
        rules = write(self.home / "rules" / "codex-harness-safe.rules", old_stamp("rule\n", "hash") + "mine\n")
        lines = self.run_migrate()
        self.assertTrue(rules.exists())
        self.assertIn(f"left {rules}: edited by hand", lines)

    def test_old_hook_entries_go_from_hooks_json_and_claude_settings(self):
        self.old_codex_state()
        settings = self.old_claude_state()
        self.run_migrate()
        for path in (self.home / "hooks.json", settings):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("codex-harness", text)
            self.assertIn('"mine"', text)
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8"))["model"], "opus")
        self.assertIn(install.HOOK_STATUS, (self.home / "hooks.json").read_text(encoding="utf-8"))

    def test_dangling_links_into_the_old_checkout_become_copies(self):
        old = self.root / "PROJECTS" / "codex-harness" / "skills"
        claude = self.user / ".claude" / "skills"
        self.link(claude / "grilling", old / "grilling")
        self.link(claude / "gone-skill", old / "gone-skill")
        self.link(self.skills / "bug-hunt", old / "bug-hunt")
        lines = self.run_migrate()
        for d in (claude / "grilling", self.skills / "bug-hunt"):
            self.assertFalse(d.is_symlink())
            self.assertTrue((d / "SKILL.md").is_file())
            self.assertTrue((d / install.SKILL_SIDECAR).is_file())
        self.assertFalse(os.path.lexists(claude / "gone-skill"))
        self.assertTrue(any("gone-skill" in line for line in lines), lines)
        self.assertFalse((claude / "codegen").exists())

    def test_dev_harness_links_for_shared_skills_become_copies_and_others_stay(self):
        dev = self.root / "PROJECTS" / "dev-harness" / "skills"
        write(dev / "private" / "SKILL.md", "x\n")
        claude = self.user / ".claude" / "skills"
        self.link(claude / "web-consensus", dev / "web-consensus")
        self.link(claude / "private", dev / "private")
        self.run_migrate()
        self.assertFalse((claude / "web-consensus").is_symlink())
        self.assertTrue((claude / "web-consensus" / "SKILL.md").is_file())
        self.assertTrue((claude / "private").is_symlink())

    def test_sidecars_are_renamed(self):
        claude = self.user / ".claude" / "skills"
        old = write(claude / "mine" / ".codex-harness", "abc\n")
        both = write(self.skills / "other" / ".codex-harness", "abc\n")
        write(self.skills / "other" / ".code-jig", "def\n")
        migrate.move_skill_sidecars([claude, self.skills])
        self.assertFalse(old.exists())
        self.assertEqual((claude / "mine" / ".code-jig").read_text(encoding="utf-8"), "abc\n")
        self.assertEqual((self.skills / "other" / ".code-jig").read_text(encoding="utf-8"), "def\n")
        self.assertEqual(migrate.pending(self.home), [])

    def test_known_launcher_is_replaced_and_unknown_is_reported(self):
        bins = self.bin_dir()
        known = write(bins / "harness", '#!/bin/sh\nexport CODEX_HARNESS_OVERLAY="$HOME/ov"\n'
                      'PYTHONPATH="$HOME/PROJECTS/codex-harness" exec python3 -m harness "$@"\n')
        unknown = write(bins / "harness.cmd", "@echo off\nsomething else\n")
        lines = self.run_migrate()
        self.assertFalse(known.exists())
        self.assertTrue(unknown.exists())
        self.assertIn(f"delete {unknown} yourself: not a known launcher", lines)
        for path in self.launchers():
            text = path.read_text(encoding="utf-8")
            self.assertIn("code-jig launcher ", text)
            self.assertIn(str(paths.CORE), text)
            self.assertIn(str(self.ov.root), text)

    def test_leftovers_are_printed_not_edited(self):
        rc = write(self.user / ".bashrc", "alias x=y\nexport CODEX_HARNESS_OVERLAY=~/ov\n")
        conf = write(self.user / ".config" / "tool" / "deep" / "c.toml", 'path = "~/.codex/codex-harness/lib"\n')
        too_deep = write(self.user / ".config" / "a" / "b" / "c" / "d.json", '"codex-harness"\n')
        big = write(self.user / ".config" / "big.json", "codex-harness" + " " * 1_100_000)
        ps = write(self.user / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1", "codex-harness\n")
        before = {p: p.read_bytes() for p in (rc, conf, too_deep, big, ps)}
        lines = self.run_migrate()
        self.assertIn(f"still names old paths: {rc}:2", lines)
        self.assertIn(f"still names old paths: {conf}:1", lines)
        self.assertIn(f"still names old paths: {ps}:1", lines)
        self.assertFalse(any(str(too_deep) in line or str(big) in line for line in lines), lines)
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_second_run_reports_nothing_to_do(self):
        self.old_codex_state()
        self.old_claude_state()
        git("config", "--global", "codexharness.email", "a@example.com")
        self.run_migrate()
        self.assertEqual(self.run_migrate(), ["nothing to do"])

    def test_interrupted_run_finishes_on_the_next(self):
        self.old_codex_state()
        real = install.run
        calls = []

        def flaky(*args):
            calls.append(1)
            if len(calls) == 1:
                raise OSError("interrupted")
            return real(*args)

        with mock.patch.object(install, "run", flaky):
            with self.assertRaises(OSError):
                self.run_migrate()
            self.run_migrate()
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(p.exists() for p in self.launchers()))
        self.assertTrue(install.is_generated(self.home / "AGENTS.md"))
        self.assertEqual(self.run_migrate(), ["nothing to do"])

    def doctor_lines(self) -> list[str]:
        write(self.root / "ov" / "overlay.toml", 'core_version = "v1"\ncore_writable = true\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            __main__.main(["--overlay", str(self.root / "ov"), "--codex-home", str(self.home), "doctor"])
        return [line for line in out.getvalue().splitlines() if line.startswith("FAIL old state:")]

    def test_doctor_fails_while_old_state_remains_and_passes_after_migrate(self):
        self.old_codex_state()
        self.old_claude_state()
        write(self.skills / "mine" / ".codex-harness", "abc\n")
        git("config", "--global", "codexharness.email", "a@example.com")
        git("config", "--global", "core.hooksPath", str(migrate.old_state(self.home) / "git-hooks"))
        found = self.doctor_lines()
        self.assertEqual(len(found), len(migrate.pending(self.home)))
        self.assertGreaterEqual(len(found), 9)
        self.assertTrue(all(line.endswith("; run code-jig migrate") for line in found), found)
        self.run_migrate()
        self.assertEqual(self.doctor_lines(), [])

    def windows(self):
        bs = migrate._bootstrap(paths.CORE)
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(bs, "os", types.SimpleNamespace(**{**vars(os), "name": "nt"})))
        stack.enter_context(mock.patch.object(install, "os", types.SimpleNamespace(path=ntpath)))
        stack.enter_context(mock.patch.object(doctor, "resolve_codex_bin", return_value=None))
        return stack

    def test_windows_home_without_codex(self):
        settings = self.old_claude_state()
        hooks = str(migrate.old_state(self.home) / "git-hooks").replace("/", "\\").upper()
        git("config", "--global", "core.hooksPath", hooks)
        git("config", "--global", "codexharness.email", "a@example.com")
        git("config", "--global", "codexharness.allowProse", "true")
        with self.windows():
            old_bin = migrate._bootstrap(paths.CORE).data_dir(None).parent / "codex-harness" / "bin"
            launcher = write(old_bin / "harness.cmd", "@echo off\nrem codex-harness launcher v0.11.0\n")
            lines = self.run_migrate()
            self.assertFalse(launcher.exists())
            self.assertTrue(all(p.suffix == ".cmd" and p.exists() for p in self.launchers()))
            self.assertEqual(migrate.pending(self.home), [])
        self.assertNotIn("codex-harness", settings.read_text(encoding="utf-8"))
        self.assertEqual(git("config", "--global", "--get-regexp", "^codexharness[.]").stdout, "")
        self.assertEqual(values("codejig.allowProse"), ["true"])
        self.assertFalse(any(line.startswith(("refused:", "failed:")) for line in lines), lines)

    def test_codex_and_claude_state_on_one_home_both_go(self):
        self.old_codex_state()
        settings = self.old_claude_state()
        old = self.root / "PROJECTS" / "codex-harness" / "skills"
        self.link(self.user / ".claude" / "skills" / "grilling", old / "grilling")
        write(self.skills / "codegen" / ".codex-harness", "abc\n")
        lines = self.run_migrate()
        self.assertFalse(any(line.startswith(("refused:", "failed:")) for line in lines), lines)
        self.assertEqual(migrate.pending(self.home), [])
        self.assertNotIn("codex-harness", settings.read_text(encoding="utf-8"))
        self.assertNotIn("codex-harness", (self.home / "hooks.json").read_text(encoding="utf-8"))
        self.assertFalse((self.user / ".claude" / "skills" / "grilling").is_symlink())

    def test_an_empty_allow_prose_is_copied_as_true(self):
        self.gitconfig.write_text("[codexharness]\n\tallowProse\n", encoding="utf-8")
        self.run_migrate()
        self.assertEqual(git("config", "--global", "--bool", "codejig.allowProse").stdout.strip(), "true")


def old_stamp(body: str, style: str = "md") -> str:
    head, tail = install.STYLES[style]
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return f"{head}generated by codex-harness sha256:{digest}{install.MARKER_NOTE}{tail}\n{body}"


def old_hook(status: str) -> dict:
    return {"hooks": [{"type": "command", "command": "x", "statusMessage": status}]}


if __name__ == "__main__":
    unittest.main()
