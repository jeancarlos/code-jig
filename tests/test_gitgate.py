# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import contextlib
import io
import os
import shlex
import stat
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from codejig import gitgate
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

    def test_strips_invisible_characters(self):
        path = write(tree(self) / "MSG", f"fix: a{ZWSP} b\n")
        in_repo(path.parent, gitgate.commit_msg, str(path))
        self.assertEqual(path.read_text(encoding="utf-8"), "fix: a b\n")

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
        self.stage({"a?.md": f"glob{ZWSP}\n", "a!.md": "bang\n"})
        in_repo(self.repo, gitgate.pre_commit, False)
        self.assertEqual(git(self.repo, "show", ":a?.md"), "glob")
        self.assertEqual(git(self.repo, "show", ":a!.md"), "bang")

    def test_a_rename_into_prose_is_refused_and_cleaned(self):
        commit(self.repo, "add\n", ME, {"notes.py": f"x{ZWSP}\n"}, 1_700_000_100)
        git(self.repo, "mv", "notes.py", "README.md")
        code, err = in_repo(self.repo, gitgate.pre_commit, True, env={"CODEX_THREAD_ID": "t"})
        self.assertEqual(code, 1)
        self.assertIn("README.md", err)
        self.assertEqual(git(self.repo, "show", ":README.md"), "x")

    def test_command_line_config_cannot_allow_prose(self):
        self.stage({"README.md": "# Hi\n"})
        env = {"CODEX_THREAD_ID": "t", "GIT_CONFIG_PARAMETERS": "'codejig.allowprose'='true'"}
        self.assertEqual(in_repo(self.repo, gitgate.pre_commit, True, env=env)[0], 1)

    def test_prose_from_an_agent_session_is_refused(self):
        self.stage({"README.md": "# Hi\n", "docs/guide.rst": "x\n", "src/app.py": "y = 2\n"})
        code, err = in_repo(self.repo, gitgate.pre_commit, True, env={"CODEX_THREAD_ID": "t"})
        self.assertEqual(code, 1)
        self.assertIn("README.md", err)
        self.assertIn("docs/guide.rst", err)
        self.assertNotIn("app.py", err)

    def test_vendored_prose_is_not_refused_for_agents(self):
        self.stage({"node_modules/dep/README.md": "# dep\n", "vendor/x/CHANGELOG.md": "- a\n"})
        self.assertEqual(in_repo(self.repo, gitgate.pre_commit, True, env={"CODEX_THREAD_ID": "t"})[0], 0)

    def test_prose_allowed_for_humans_exempt_files_and_opted_in_repos(self):
        self.stage({"README.md": "# Hi\n"})
        self.assertEqual(in_repo(self.repo, gitgate.pre_commit, True)[0], 0)
        self.assertEqual(in_repo(self.repo, gitgate.pre_commit, False, env={"CLAUDECODE": "1"})[0], 0)
        git(self.repo, "config", "codejig.allowProse", "true")
        self.assertEqual(in_repo(self.repo, gitgate.pre_commit, True, env={"CLAUDECODE": "1"})[0], 0)

    def test_invisible_chars_in_code_or_data_are_refused_for_agents_and_left_for_humans(self):
        files = {"app.js": f'const s = "a{ZWSP}b";\n', "a.py": f'S = "{ZWSP}"\n', "d.json": f'{{"k": "{ZWSP}"}}\n'}
        self.stage(files)
        code, err = in_repo(self.repo, gitgate.pre_commit, False, env={"CODEX_THREAD_ID": "t"})
        self.assertEqual(code, 1)
        for name in ("app.js:1", "a.py:1", "d.json:1"):
            self.assertIn(name, err)
        code, err = in_repo(self.repo, gitgate.pre_commit, False)
        self.assertEqual(code, 0)
        self.assertIn("app.js:1", err)
        for name, text in files.items():
            self.assertEqual(git(self.repo, "show", f":{name}"), text.rstrip("\n"))
            self.assertEqual((self.repo / name).read_text(encoding="utf-8"), text)

    @unittest.skipIf(os.name == "nt", "symlinks")
    def test_the_worktree_fix_never_writes_through_a_linked_folder(self):
        self.stage({"sub/a.py": f"x = 1{ZWSP}\n"})
        outside = tree(self)
        victim = write(outside / "a.py", f"mine{ZWSP}\n")
        (self.repo / "sub" / "a.py").unlink()
        (self.repo / "sub").rmdir()
        (self.repo / "sub").symlink_to(outside, target_is_directory=True)
        code, _ = in_repo(self.repo, gitgate.pre_commit, False)
        self.assertEqual(code, 0)
        self.assertEqual(git(self.repo, "show", ":sub/a.py"), "x = 1")
        self.assertEqual(victim.read_text(encoding="utf-8"), f"mine{ZWSP}\n")

    @unittest.skipIf(os.name == "nt", "symlinks")
    def test_a_symlink_replaced_by_prose_is_seen(self):
        (self.repo / "README.md").symlink_to("base.py")
        commit(self.repo, "link\n", ME, {}, 1_700_000_100)
        (self.repo / "README.md").unlink()
        self.stage({"README.md": f"# x{ZWSP}\n"})
        code, err = in_repo(self.repo, gitgate.pre_commit, True, env={"CODEX_THREAD_ID": "t"})
        self.assertEqual(code, 1)
        self.assertIn("README.md", err)
        self.assertEqual(git(self.repo, "show", ":README.md"), "# x")

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
        self.assertIn("not on any remote yet", err)
        self.assertNotIn("scrub", err)

    def test_refuses_a_zero_width_space_only(self):
        repo = new_repo(self)
        base = commit(repo, "init\n", ME, {"a": "1\n"}, 1_700_000_000)
        tip = commit(repo, f"mine{ZWSP}\n", ME, {"c": "1\n"}, 1_700_000_200)
        self.assertEqual(in_repo(repo, gitgate.pre_push, [f"refs/heads/main {tip} refs/heads/main {base}"])[0], 1)

    def test_unknown_remote_tip_falls_back_to_unpushed_commits(self):
        repo = new_repo(self)
        tip = commit(repo, f"mine\n\n{CODEX}\n", ME, {"c": "1\n"}, 1_700_000_200)
        self.assertEqual(in_repo(repo, gitgate.pre_push, [f"refs/heads/main {tip} refs/heads/main {'1' * 40}"])[0], 1)

    def test_merge_commit_messages_are_checked(self):
        repo = new_repo(self)
        base = commit(repo, "init\n", ME, {"a": "1\n"}, 1_700_000_000)
        side = commit(repo, "side\n", ME, {"b": "1\n"}, 1_700_000_100)
        env = {"GIT_AUTHOR_NAME": "me", "GIT_AUTHOR_EMAIL": ME, "GIT_COMMITTER_NAME": "me", "GIT_COMMITTER_EMAIL": ME}
        merge = git(repo, "commit-tree", git(repo, "rev-parse", f"{side}^{{tree}}"), "-p", side, "-p", base, "-F", "-",
                    stdin=f"Merge x\n\n{CODEX}\n", env=env)
        git(repo, "update-ref", "HEAD", merge)
        code, err = in_repo(repo, gitgate.pre_push, [f"refs/heads/main {merge} refs/heads/main {side}"])
        self.assertEqual(code, 1)
        self.assertIn(merge[:10], err)

    def test_deletions_and_new_branches(self):
        repo = new_repo(self)
        tip = commit(repo, f"mine\n\n{CODEX}\n", ME, {"c": "1\n"}, 1_700_000_200)
        zero = "0" * 40
        self.assertEqual(in_repo(repo, gitgate.pre_push, [f"(delete) {zero} refs/heads/x {tip}"])[0], 0)
        self.assertEqual(in_repo(repo, gitgate.pre_push, [f"refs/heads/main {tip} refs/heads/main {zero}"])[0], 1)

    def test_a_sha256_deletion_is_not_read_as_a_commit_push(self):
        repo = new_repo(self)
        tip = commit(repo, f"mine\n\n{CODEX}\n", ME, {"c": "1\n"}, 1_700_000_200)
        self.assertEqual(in_repo(repo, gitgate.pre_push, [f"(delete) {'0' * 64} refs/heads/x {tip}"])[0], 0)
        self.assertFalse(gitgate._known("0" * 64))


class PrePushTests(unittest.TestCase):
    def setUp(self):
        self.repo = new_repo(self)
        self.base = commit(self.repo, "init\n", ME, {"a": "1\n"}, 1_700_000_000)

    def line(self, message="next\n"):
        tip = commit(self.repo, message, ME, {"b": "1\n"}, 1_700_000_100)
        return f"refs/heads/main {tip} refs/heads/main {self.base}"

    def command(self, rc):
        return f'"{sys.executable}" -c "open(\'ran\', \'w\'); raise SystemExit({rc})"'

    def push(self, line, env=None):
        return in_repo(self.repo, gitgate.pre_push, [line], env=env)

    def test_pre_push_runs_the_test_command_and_refuses_on_failure(self):
        git(self.repo, "config", "codejig.testCommand", self.command(3))
        code, err = self.push(self.line())
        self.assertEqual(code, 1)
        self.assertIn("code-jig: push refused, tests fail", err)
        self.assertIn("exited 3", err)
        self.assertTrue((self.repo / "ran").exists())

    def test_pre_push_passes_when_the_test_command_passes(self):
        git(self.repo, "config", "codejig.testCommand", self.command(0))
        self.assertEqual(self.push(self.line())[0], 0)
        self.assertTrue((self.repo / "ran").exists())

    def test_pre_push_without_a_test_command_runs_nothing(self):
        self.assertEqual(self.push(self.line())[0], 0)
        self.assertFalse((self.repo / "ran").exists())

    def test_skip_env_skips_with_a_notice(self):
        git(self.repo, "config", "codejig.testCommand", self.command(1))
        code, err = self.push(self.line(), env={"CODE_JIG_SKIP_TESTS": "1"})
        self.assertEqual(code, 0)
        self.assertIn("CODE_JIG_SKIP_TESTS", err)
        self.assertFalse((self.repo / "ran").exists())

    def test_attribution_refusal_happens_before_tests(self):
        git(self.repo, "config", "codejig.testCommand", self.command(0))
        code, err = self.push(self.line(f"mine\n\n{CODEX}\n"))
        self.assertEqual(code, 1)
        self.assertIn("AI attribution", err)
        self.assertFalse((self.repo / "ran").exists())

    def test_test_command_does_not_inherit_the_hook_git_environment(self):
        cmd = f'"{sys.executable}" -c "import os; open(\'ran\', \'w\').write(os.environ.get(\'GIT_DIR\') or \'\')"'
        git(self.repo, "config", "codejig.testCommand", cmd)
        self.assertEqual(self.push(self.line(), env={"GIT_DIR": str(self.repo / ".git")})[0], 0)
        self.assertEqual((self.repo / "ran").read_text(), "")

    def test_a_configured_command_without_a_top_level_fails_closed(self):
        bare = tree(self) / "bare"
        bare.mkdir()
        git(bare, "init", "-q", "--bare")
        git(bare, "config", "codejig.testCommand", self.command(0))
        code, err = in_repo(bare, gitgate.pre_push, [])
        self.assertEqual(code, 1)
        self.assertIn("cannot find the repo top level", err)


class PushCleanup(unittest.TestCase):
    def setUp(self):
        self.repo = new_repo(self)
        self.base = commit(self.repo, "init\n", ME, {"a": "1\n"}, 1_700_000_000)
        origin = tree(self) / "origin.git"
        git(origin.parent, "init", "-q", "--bare", str(origin))
        git(self.repo, "remote", "add", "origin", str(origin))
        git(self.repo, "push", "-q", "origin", "main")

    def push(self, tip, ref="refs/heads/main", cleanup=True, remote=None):
        return in_repo(self.repo, gitgate.pre_push, [f"{ref} {tip} refs/heads/main {remote or self.base}"], cleanup)

    def messages(self):
        return git(self.repo, "log", "--format=%B%x1e", "main").split("\x1e")

    def test_pre_push_cleans_outgoing_commits_and_asks_to_push_again(self):
        commit(self.repo, f"mine\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        tip = commit(self.repo, "next\n", ME, {"c": "1\n"}, 1_700_000_200)
        trees = git(self.repo, "log", "--format=%T %ad %cd", "main")
        code, err = self.push(tip)
        self.assertEqual(code, 1)
        self.assertIn("code-jig: cleaned AI attribution from 1 commits on main; backup ", err)
        self.assertIn("; run the same push again", err)
        bundle = Path(err.split("backup ", 1)[1].split("; run", 1)[0])
        self.assertTrue(bundle.is_file())
        self.assertNotIn(CODEX, "".join(self.messages()))
        self.assertEqual(git(self.repo, "log", "--format=%T %ad %cd", "main"), trees)
        self.assertEqual(git(self.repo, "rev-parse", "main~2"), self.base)

    def test_second_push_after_cleanup_passes(self):
        tip = commit(self.repo, f"mine\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        self.assertEqual(self.push(tip)[0], 1)
        new = git(self.repo, "rev-parse", "main")
        self.assertNotEqual(new, tip)
        self.assertEqual(self.push(new), (0, ""))
        git(self.repo, "push", "-q", "origin", "main")
        self.assertEqual(git(self.repo, "log", "-1", "--format=%B", "origin/main"), "mine")

    def test_cleanup_never_rewrites_commits_already_on_a_remote(self):
        dirty = commit(self.repo, f"mine\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        git(self.repo, "push", "-q", "origin", "main:feature")
        tip = commit(self.repo, "next\n", ME, {"c": "1\n"}, 1_700_000_200)
        code, err = self.push(tip)
        self.assertEqual(code, 1)
        self.assertIn("push refused", err)
        self.assertIn(f"{dirty[:10]} mine [locked: already on a remote]", err)
        self.assertIn("never rewrites them", err)
        self.assertNotIn("not on any remote yet", err)
        self.assertNotIn("scrub", err)
        self.assertEqual(git(self.repo, "rev-parse", "main"), tip)
        self.assertEqual(git(self.repo, "rev-parse", "main~1"), dirty)

    def assert_refused(self, tip, **kw):
        code, err = self.push(tip, **kw)
        self.assertEqual(code, 1)
        self.assertIn("push refused", err)
        self.assertIn("not on any remote yet", err)
        self.assertNotIn("cleaned", err)
        self.assertEqual(git(self.repo, "rev-parse", "main"), tip)
        return err

    def test_cleanup_leaves_tags_and_other_authors_to_the_refusal(self):
        tip = commit(self.repo, f"mine\n\n{CODEX}\n", ME, {"c": "1\n"}, 1_700_000_200)
        git(self.repo, "tag", "v1")
        for ref in ("refs/tags/v1", tip):
            self.assert_refused(tip, ref=ref)
        commit(self.repo, "theirs\n", OTHER, {"d": "1\n"}, 1_700_000_300)
        self.assert_refused(git(self.repo, "rev-parse", "main"))

    def test_a_signed_commit_in_the_range_keeps_the_refusal(self):
        commit(self.repo, f"mine\n\n{CODEX}\n", ME, {"c": "1\n"}, 1_700_000_200)
        env = {**os.environ, **ENV}
        head, _, msg = subprocess.run(["git", "-C", str(self.repo), "cat-file", "commit", "HEAD"], capture_output=True,
                                      env=env, check=True).stdout.partition(b"\n\n")
        sig = b"gpgsig -----BEGIN PGP SIGNATURE-----\n \n iQEz\n -----END PGP SIGNATURE-----"
        signed = subprocess.run(["git", "-C", str(self.repo), "hash-object", "-t", "commit", "-w", "--stdin"],
                                input=head + b"\n" + sig + b"\n\n" + msg, capture_output=True, env=env,
                                check=True).stdout.decode().strip()
        self.assertIn(b"gpgsig", subprocess.run(["git", "-C", str(self.repo), "cat-file", "commit", signed],
                                                capture_output=True, env=env, check=True).stdout)
        git(self.repo, "update-ref", "refs/heads/main", signed)
        self.assertNotIn("aborted", self.assert_refused(signed))

    def test_push_of_head_resolves_to_the_branch(self):
        tip = commit(self.repo, f"mine\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        code, err = self.push(tip, ref="HEAD")
        self.assertEqual(code, 1)
        self.assertIn("cleaned AI attribution from 1 commits on main", err)
        self.assertEqual(git(self.repo, "log", "-1", "--format=%B", "main"), "mine")

    def test_a_branch_being_rebased_keeps_the_refusal(self):
        tip = commit(self.repo, f"mine\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        gitdir = Path(git(self.repo, "rev-parse", "--absolute-git-dir"))
        write(gitdir / "rebase-merge" / "head-name", "refs/heads/main\n")
        self.assert_refused(tip)
        (gitdir / "rebase-merge" / "head-name").unlink()
        (gitdir / "rebase-merge").rmdir()
        git(self.repo, "branch", "side", self.base)
        other = self.repo.parent / "wt"
        git(self.repo, "worktree", "add", "-q", str(other), "side")
        wt_gitdir = Path(git(other, "rev-parse", "--absolute-git-dir"))
        write(wt_gitdir / "rebase-apply" / "head-name", "refs/heads/main\n")
        self.assert_refused(tip)

    def test_a_branch_moved_by_a_stopped_update_refs_rebase_keeps_the_refusal(self):
        topic = commit(self.repo, f"topic\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        git(self.repo, "branch", "topic")
        commit(self.repo, "feature\n", ME, {"f": "1\n"}, 1_700_000_200)
        git(self.repo, "branch", "feature")
        git(self.repo, "reset", "-q", "--hard", self.base)
        wt = self.repo.parent / "wt"
        git(self.repo, "worktree", "add", "-q", str(wt), "feature")
        editor = write(self.repo.parent / "edit.py", "import sys, pathlib\n"
                       "p = pathlib.Path(sys.argv[1])\n"
                       "p.write_text(p.read_text().replace('pick', 'edit', 1))\n")
        git(wt, "rebase", "-q", "-i", "--update-refs", self.base,
            env={"GIT_SEQUENCE_EDITOR": f'"{Path(sys.executable).as_posix()}" "{editor.as_posix()}"'})
        self.assertTrue(list(Path(git(wt, "rev-parse", "--absolute-git-dir")).glob("rebase-merge/update-refs")))
        code, err = in_repo(self.repo, gitgate.pre_push, [f"refs/heads/topic {topic} refs/heads/topic {self.base}"], True)
        self.assertEqual(code, 1)
        self.assertNotIn("cleaned", err)
        self.assertEqual(git(self.repo, "rev-parse", "topic"), topic)

    def test_a_git_am_in_progress_keeps_the_refusal_for_the_checked_out_branch(self):
        tip = commit(self.repo, f"mine\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        write(Path(git(self.repo, "rev-parse", "--absolute-git-dir")) / "rebase-apply" / "applying", "")
        self.assert_refused(tip)

    def two_branches(self):
        main = commit(self.repo, f"mine\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        git(self.repo, "checkout", "-q", "-b", "feature/x", self.base)
        feature = commit(self.repo, f"feat\n\n{CODEX}\n", ME, {"f": "1\n"}, 1_700_000_200)
        git(self.repo, "checkout", "-q", "main")
        lines = [f"refs/heads/main {main} refs/heads/main {self.base}",
                 f"refs/heads/feature/x {feature} refs/heads/feature/x {'0' * 40}"]
        return main, feature, lines

    def test_two_branches_cleaned_in_one_push_keep_both_backups(self):
        main, feature, lines = self.two_branches()
        code, err = in_repo(self.repo, gitgate.pre_push, lines, True)
        self.assertEqual(code, 1)
        bundles = [Path(ln.split("backup ", 1)[1].split("; run", 1)[0]) for ln in err.splitlines() if "backup " in ln]
        self.assertEqual(len(set(bundles)), 2)
        heads = [git(self.repo, "bundle", "list-heads", str(b)) for b in bundles]
        self.assertIn(main, heads[0])
        self.assertIn("refs/heads/main", heads[0])
        self.assertIn(feature, heads[1])
        self.assertIn("refs/heads/feature/x", heads[1])

    def test_a_later_branch_failing_rolls_back_the_whole_push(self):
        from codejig import scrub
        main, feature, lines = self.two_branches()
        real, calls = scrub.rewrite_stream, []

        def flaky(stream, emails):
            calls.append(1)
            if len(calls) == 2:
                raise scrub.Abort("boom")
            return real(stream, emails)
        with mock.patch.object(scrub, "rewrite_stream", flaky):
            code, err = in_repo(self.repo, gitgate.pre_push, lines, True)
        self.assertEqual(code, 1)
        self.assertNotIn("cleaned", err)
        self.assertIn("push refused", err)
        self.assertEqual((git(self.repo, "rev-parse", "main"), git(self.repo, "rev-parse", "feature/x")), (main, feature))

    def test_cleanup_off_or_git_config_false_keeps_the_refusal(self):
        tip = commit(self.repo, f"mine\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        code, err = self.push(tip, cleanup=False)
        self.assertEqual(code, 1)
        self.assertIn("codejig.pushCleanup true", err)
        git(self.repo, "config", "codejig.pushCleanup", "false")
        self.assertIn("push refused", self.push(tip)[1])
        self.assertEqual(git(self.repo, "rev-parse", "main"), tip)
        git(self.repo, "config", "codejig.pushCleanup", "true")
        self.assertIn("cleaned AI attribution", self.push(tip, cleanup=False)[1])


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
                           capture_output=True, text=True, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("README.md", r.stderr)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) & 0o100 for p in hooks.iterdir()))

    def test_real_push_through_the_shims_cleans_then_passes(self):
        hooks = tree(self) / "git-hooks"
        for name, text in gitgate.shims(Path(__file__).resolve().parent.parent, sys.executable, False, cleanup=True).items():
            write(hooks / name, text)
            os.chmod(hooks / name, 0o755)
        repo = new_repo(self)
        origin = repo.parent / "origin.git"
        git(repo.parent, "init", "-q", "--bare", str(origin))
        git(repo, "remote", "add", "origin", str(origin))
        commit(repo, "init\n", ME, {"a": "1\n"}, 1_700_000_000)
        git(repo, "push", "-q", "origin", "main")
        commit(repo, f"mine\n\n{CODEX}\n", ME, {"b": "1\n"}, 1_700_000_100)
        git(repo, "config", "core.hooksPath", str(hooks))
        push = ["git", "-C", str(repo), "push", "-q", "origin", "main"]
        env = {**NO_AGENT, **ENV}
        first = subprocess.run(push, env=env, capture_output=True, text=True, check=False)
        self.assertNotEqual(first.returncode, 0)
        self.assertIn("cleaned AI attribution from 1 commits on main", first.stderr)
        second = subprocess.run(push, env=env, capture_output=True, text=True, check=False)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(git(repo, "log", "-1", "--format=%B", "origin/main"), "mine")


class Cli(unittest.TestCase):
    def test_unknown_hook_is_a_no_op(self):
        self.assertEqual(gitgate.cli(types.SimpleNamespace(name="post-checkout", rest=[], prose=False, cleanup=False)), 0)

    def hook(self, cwd, name, stdin=""):
        args = types.SimpleNamespace(name=name, rest=[], prose=False, cleanup=False)
        with mock.patch.object(sys, "stdin", io.StringIO(stdin)):
            return in_repo(cwd, gitgate.cli, args)

    def test_a_git_error_in_pre_push_refuses_the_push(self):
        repo = new_repo(self)
        base = commit(repo, "init\n", ME, {"a": "1\n"}, 1_700_000_000)
        code, err = self.hook(repo, "pre-push", f"refs/heads/main {'1' * 40} refs/heads/main {base}\n")
        self.assertEqual(code, 1)
        self.assertIn("push refused", err)

    def test_a_git_error_in_pre_commit_refuses_the_commit(self):
        code, err = self.hook(tree(self), "pre-commit")
        self.assertEqual(code, 1)
        self.assertIn("refused", err)

    def test_a_push_without_an_identity_is_refused(self):
        repo = new_repo(self)
        git(repo, "config", "--unset", "user.email")
        tip = commit(repo, f"mine\n\n{CODEX}\n", ME, {"a": "1\n"}, 1_700_000_000)
        code, err = self.hook(repo, "pre-push", f"refs/heads/main {tip} refs/heads/main {'0' * 40}\n")
        self.assertEqual(code, 1)
        self.assertIn("user.email", err)

    def test_scrub_is_not_a_core_command(self):
        from codejig.__main__ import COMMAND_MODULES, build_parser
        self.assertNotIn("scrub", COMMAND_MODULES)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(["scrub"])

    def test_pre_push_shim_passes_the_cleanup_flag(self):
        self.assertIn("git-hook --cleanup pre-push", gitgate.shims(Path("lib"), "python", False, cleanup=True)["pre-push"])
        self.assertNotIn("--cleanup", gitgate.shims(Path("lib"), "python", False)["pre-push"])

    def test_shim_argv_parses_with_git_hook_arguments(self):
        from codejig.__main__ import build_parser
        hooks = gitgate.shims(Path("lib"), "python", True, cleanup=True)
        for name, git_args, flag in (("pre-push", ["origin", "https://example.com/r.git"], "cleanup"),
                                     ("pre-commit", [], "prose"), ("commit-msg", [".git/COMMIT_EDITMSG"], None)):
            line = next(ln for ln in hooks[name].splitlines() if "-m codejig git-hook" in ln)
            words = shlex.split(line.split("-m codejig ", 1)[1].split("||", 1)[0])
            argv = [w for w in words if w != "$@"] + git_args
            args = build_parser().parse_args(argv)
            self.assertEqual((args.name, args.rest), (name, git_args))
            if flag:
                self.assertTrue(getattr(args, flag))


if __name__ == "__main__":
    unittest.main()
