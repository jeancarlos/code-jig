import contextlib
import io
import os
import stat
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from harness import gitgate
from tests.test_scrub import CODEX, ENV, ME, OTHER, commit, git, new_repo
from tests.util import tree, write

EM_DASH, ZWSP = chr(0x2014), chr(0x200B)
NO_AGENT = {k: v for k, v in os.environ.items() if k not in gitgate.AGENT_ENV}


def in_repo(repo: Path, fn, *args, env: dict | None = None):
    old = os.getcwd()
    os.chdir(repo)
    err = io.StringIO()
    try:
        with mock.patch.dict(os.environ, {**NO_AGENT, **ENV, **(env or {})}, clear=True), contextlib.redirect_stderr(err):
            return fn(*args), err.getvalue()
    finally:
        os.chdir(old)


class CommitMsg(unittest.TestCase):
    def test_strips_attribution_and_dashes(self):
        path = write(tree(self) / "MSG", f"fix: a {EM_DASH} b\n\n{CODEX}\n")
        code, _ = in_repo(path.parent, gitgate.commit_msg, str(path))
        self.assertEqual((code, path.read_text(encoding="utf-8")), (0, "fix: a - b\n"))

    def test_clean_message_is_untouched(self):
        path = write(tree(self) / "MSG", "fix: plain\n")
        before = path.stat().st_mtime_ns
        in_repo(path.parent, gitgate.commit_msg, str(path))
        self.assertEqual(path.stat().st_mtime_ns, before)


class PreCommit(unittest.TestCase):
    def setUp(self):
        self.repo = new_repo(self)
        commit(self.repo, "init\n", ME, {"base.py": "x = 1\n"}, 1_700_000_000)

    def stage(self, files: dict[str, str]):
        for name, text in files.items():
            write(self.repo / name, text)
        git(self.repo, "add", "-A")

    def test_invisible_chars_fixed_in_index_and_worktree(self):
        self.stage({"a.py": f"x = 1{ZWSP}\n", "notes.md": f"a {EM_DASH} b{ZWSP}\n", "Co.py": "# Co-authored-by: Codex\n"})
        code, err = in_repo(self.repo, gitgate.pre_commit, False)
        self.assertEqual(code, 0)
        self.assertEqual(git(self.repo, "show", ":a.py"), "x = 1")
        self.assertEqual((self.repo / "a.py").read_text(encoding="utf-8"), "x = 1\n")
        self.assertEqual(git(self.repo, "show", ":notes.md"), "a - b")
        self.assertIn("Co-authored-by", git(self.repo, "show", ":Co.py"))
        self.assertIn("a.py", err)

    @unittest.skipIf(os.name == "nt", "? is not a valid Windows file name")
    def test_a_file_named_like_a_pathspec_keeps_its_own_content(self):
        self.stage({"a?": f"glob{ZWSP}\n", "a!": "bang\n"})
        in_repo(self.repo, gitgate.pre_commit, False)
        self.assertEqual(git(self.repo, "show", ":a?"), "glob")
        self.assertEqual(git(self.repo, "show", ":a!"), "bang")

    def test_a_rename_into_prose_is_refused_and_cleaned(self):
        commit(self.repo, "add\n", ME, {"notes.py": f"x{ZWSP}\n"}, 1_700_000_100)
        git(self.repo, "mv", "notes.py", "README.md")
        code, err = in_repo(self.repo, gitgate.pre_commit, True, env={"CODEX_THREAD_ID": "t"})
        self.assertEqual(code, 1)
        self.assertIn("README.md", err)
        self.assertEqual(git(self.repo, "show", ":README.md"), "x")

    def test_command_line_config_cannot_allow_prose(self):
        self.stage({"README.md": "# Hi\n"})
        env = {"CODEX_THREAD_ID": "t", "GIT_CONFIG_PARAMETERS": "'codexharness.allowprose'='true'"}
        self.assertEqual(in_repo(self.repo, gitgate.pre_commit, True, env=env)[0], 1)

    def test_prose_from_an_agent_session_is_refused(self):
        self.stage({"README.md": "# Hi\n", "docs/guide.rst": "x\n", "src/app.py": "y = 2\n"})
        code, err = in_repo(self.repo, gitgate.pre_commit, True, env={"CODEX_THREAD_ID": "t"})
        self.assertEqual(code, 1)
        self.assertIn("README.md", err)
        self.assertIn("docs/guide.rst", err)
        self.assertNotIn("app.py", err)

    def test_prose_allowed_for_humans_exempt_files_and_opted_in_repos(self):
        self.stage({"README.md": "# Hi\n"})
        self.assertEqual(in_repo(self.repo, gitgate.pre_commit, True)[0], 0)
        self.assertEqual(in_repo(self.repo, gitgate.pre_commit, False, env={"CLAUDECODE": "1"})[0], 0)
        git(self.repo, "config", "codexharness.allowProse", "true")
        self.assertEqual(in_repo(self.repo, gitgate.pre_commit, True, env={"CLAUDECODE": "1"})[0], 0)

    def test_agent_instruction_files_and_specs_are_not_prose(self):
        self.stage({"AGENTS.md": "x\n", "skills/a/SKILL.md": "x\n", "docs/specs/s.md": "x\n", "requirements.txt": "x\n"})
        self.assertEqual(in_repo(self.repo, gitgate.pre_commit, True, env={"CODEX_THREAD_ID": "t"})[0], 0)


class PrePush(unittest.TestCase):
    def test_refuses_my_attributed_commits_only(self):
        repo = new_repo(self)
        base = commit(repo, "init\n", ME, {"a": "1\n"}, 1_700_000_000)
        commit(repo, f"other\n\n{CODEX}\n", OTHER, {"b": "1\n"}, 1_700_000_100)
        clean_tip = git(repo, "rev-parse", "HEAD")
        line = f"refs/heads/main {clean_tip} refs/heads/main {base}"
        self.assertEqual(in_repo(repo, gitgate.pre_push, [line])[0], 0)
        tip = commit(repo, f"mine\n\n{CODEX}\n", ME, {"c": "1\n"}, 1_700_000_200)
        code, err = in_repo(repo, gitgate.pre_push, [f"refs/heads/main {tip} refs/heads/main {base}"])
        self.assertEqual(code, 1)
        self.assertIn(tip[:10], err)
        self.assertIn("harness scrub", err)

    def test_unknown_remote_tip_falls_back_to_unpushed_commits(self):
        repo = new_repo(self)
        tip = commit(repo, f"mine\n\n{CODEX}\n", ME, {"c": "1\n"}, 1_700_000_200)
        self.assertEqual(in_repo(repo, gitgate.pre_push, [f"refs/heads/main {tip} refs/heads/main {'1' * 40}"])[0], 1)

    def test_deletions_and_new_branches(self):
        repo = new_repo(self)
        tip = commit(repo, f"mine\n\n{CODEX}\n", ME, {"c": "1\n"}, 1_700_000_200)
        zero = "0" * 40
        self.assertEqual(in_repo(repo, gitgate.pre_push, [f"(delete) {zero} refs/heads/x {tip}"])[0], 0)
        self.assertEqual(in_repo(repo, gitgate.pre_push, [f"refs/heads/main {tip} refs/heads/main {zero}"])[0], 1)


@unittest.skipIf(os.name == "nt", "POSIX shell shims")
class Shims(unittest.TestCase):
    def test_real_commit_through_the_shims_chains_to_repo_hooks(self):
        root = tree(self)
        hooks = root / "git-hooks"
        lib = Path(__file__).resolve().parent.parent
        for name, text in gitgate.shims(lib, sys.executable, prose=True).items():
            write(hooks / name, text)
            os.chmod(hooks / name, 0o755)
        repo = new_repo(self)
        git(repo, "config", "core.hooksPath", str(hooks))
        local = write(Path(git(repo, "rev-parse", "--absolute-git-dir")) / "hooks" / "post-commit", "#!/bin/sh\ntouch chained\n")
        os.chmod(local, 0o755)
        write(repo / "a.py", "x = 1\n")
        git(repo, "add", "-A")
        env = {**NO_AGENT, **ENV, "GIT_AUTHOR_NAME": "me", "GIT_AUTHOR_EMAIL": ME, "GIT_COMMITTER_NAME": "me", "GIT_COMMITTER_EMAIL": ME}
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", f"add {EM_DASH} a\n\n{CODEX}"], env=env, check=True)
        self.assertEqual(git(repo, "log", "-1", "--format=%B"), "add - a")
        self.assertTrue((repo / "chained").exists())
        write(repo / "README.md", "# x\n")
        git(repo, "add", "-A")
        r = subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "docs"], env={**env, "CODEX_THREAD_ID": "t"},
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("README.md", r.stderr)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) & 0o100 for p in hooks.iterdir()))


class Cli(unittest.TestCase):
    def test_unknown_hook_is_a_no_op(self):
        self.assertEqual(gitgate.cli(types.SimpleNamespace(name="post-checkout", rest=[], prose=False)), 0)


if __name__ == "__main__":
    unittest.main()
