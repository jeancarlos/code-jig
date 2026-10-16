import contextlib
import io
import os
import subprocess
import types
import unittest
from pathlib import Path

from codejig import scrub, watermark
from tests.util import tree, write

ME, OTHER = "me@example.com", "other@example.com"
CODEX = "Co-authored-by: Codex <noreply@openai.com>"
CLAUDE = "Co-Authored-By: Claude <noreply@anthropic.com>"
ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo: Path, *args: str, stdin: str | None = None, env: dict | None = None) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                       input=stdin, env={**os.environ, **ENV, **(env or {})}, check=True)
    return r.stdout.strip()


def commit(repo: Path, message: str, email: str, files: dict[str, str], when: int) -> str:
    for name, text in files.items():
        write(repo / name, text)
    git(repo, "add", "-A")
    tree_sha = git(repo, "write-tree")
    parent = subprocess.run(["git", "-C", str(repo), "rev-parse", "-q", "--verify", "HEAD"],
                            capture_output=True, text=True, encoding="utf-8").stdout.strip()
    stamp = f"{when} +0000"
    env = {"GIT_AUTHOR_NAME": email.split("@")[0], "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": stamp,
           "GIT_COMMITTER_NAME": email.split("@")[0], "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": stamp}
    sha = git(repo, "commit-tree", tree_sha, *(["-p", parent] if parent else []), "-F", "-", stdin=message, env=env)
    git(repo, "update-ref", "HEAD", sha)
    return sha


def new_repo(test) -> Path:
    repo = tree(test) / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", ME)
    return repo


def run(repo: Path, *extra: str, dry_run: bool = False) -> tuple[int, str]:
    out = io.StringIO()
    args = types.SimpleNamespace(path=str(repo), author=list(extra), dry_run=dry_run)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = scrub.cli(args)
    return code, out.getvalue()


def history(repo: Path) -> list[tuple[str, str, str, str]]:
    out = git(repo, "log", "--format=%T%x00%an <%ae> %ad%x00%cn <%ce> %cd%x00%B%x1e", "main")
    return [tuple(r.strip("\n").split("\0")) for r in out.split("\x1e") if r.strip()]


class Scrub(unittest.TestCase):
    def setUp(self):
        self.repo = new_repo(self)
        commit(self.repo, "one\n", ME, {"a.txt": "1\n"}, 1_700_000_000)
        self.dirty = commit(self.repo, f"two\n\nbody\n\n{CODEX}\n", ME, {"a.txt": "2\n"}, 1_700_000_100)
        commit(self.repo, f"three\n\n{CLAUDE}\n", OTHER, {"b.txt": "3\n"}, 1_700_000_200)
        commit(self.repo, "four\n", ME, {"c.txt": "4\n"}, 1_700_000_300)
        git(self.repo, "tag", "light", self.dirty)
        git(self.repo, "tag", "-a", "annotated", "-m", "release", self.dirty,
            env={"GIT_COMMITTER_NAME": "me", "GIT_COMMITTER_EMAIL": ME, "GIT_COMMITTER_DATE": "1700000400 +0000"})

    def test_removes_only_my_trailers_and_changes_nothing_else(self):
        before = history(self.repo)
        write(self.repo / "a.txt", "uncommitted\n")
        code, out = run(self.repo)
        self.assertEqual(code, 0, out)
        after = history(self.repo)
        self.assertEqual([r[:3] for r in after], [r[:3] for r in before])
        self.assertEqual(after[2][3], "two\n\nbody")
        self.assertIn(CLAUDE, after[1][3])
        self.assertEqual([r[3] for r in after if r is not after[2]], [r[3] for r in before if r is not before[2]])
        self.assertEqual((self.repo / "a.txt").read_text(encoding="utf-8"), "uncommitted\n")
        self.assertIn("1 commits", out)
        self.assertTrue(list(Path(git(self.repo, "rev-parse", "--absolute-git-dir")).glob("code-jig-scrub-*.bundle")))

    def test_tags_follow_the_rewritten_commit(self):
        run(self.repo)
        new_two = git(self.repo, "rev-parse", "main~2")
        self.assertNotEqual(new_two, self.dirty)
        self.assertEqual(git(self.repo, "rev-parse", "light"), new_two)
        self.assertEqual(git(self.repo, "rev-parse", "annotated^{commit}"), new_two)

    def test_dry_run_lists_and_changes_nothing(self):
        head = git(self.repo, "rev-parse", "main")
        code, out = run(self.repo, dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn(self.dirty[:10], out)
        self.assertEqual(git(self.repo, "rev-parse", "main"), head)

    def test_extra_author_is_also_scrubbed(self):
        run(self.repo, OTHER)
        self.assertNotIn(CLAUDE, history(self.repo)[1][3])

    def test_clean_repo_is_left_alone(self):
        repo = new_repo(self)
        head = commit(repo, "plain\n", ME, {"a": "1\n"}, 1_700_000_000)
        code, out = run(repo)
        self.assertEqual((code, git(repo, "rev-parse", "main")), (0, head))
        self.assertIn("clean", out)

    def test_same_history_gives_the_same_shas(self):
        clone = self.repo.parent / "clone"
        subprocess.run(["git", "clone", "-q", str(self.repo), str(clone)], check=True, env={**os.environ, **ENV})
        git(clone, "config", "user.email", ME)
        run(self.repo)
        run(clone)
        self.assertEqual(git(self.repo, "rev-parse", "main"), git(clone, "rev-parse", "main"))
        self.assertNotEqual(git(clone, "rev-parse", "main"), git(clone, "rev-parse", "origin/main"))

    def test_a_bad_rewrite_aborts_and_restores_every_ref(self):
        from unittest import mock
        before = git(self.repo, "for-each-ref", "--format=%(refname) %(objectname)")
        real = scrub.rewrite_stream
        with mock.patch.object(scrub, "rewrite_stream", lambda stream, emails: real(stream, emails | {OTHER})):
            code, out = run(self.repo)
        self.assertEqual(code, 1)
        self.assertIn("ABORT", out)
        self.assertEqual(git(self.repo, "for-each-ref", "--format=%(refname) %(objectname)"), before)

    def test_printed_push_commands_are_shell_safe(self):
        import shlex
        git(self.repo, "branch", "x;touch$(pwned)", "main")
        clone = self.repo.parent / "clone"
        subprocess.run(["git", "clone", "-q", "--no-local", str(self.repo), str(clone)], check=True, env={**os.environ, **ENV})
        git(clone, "config", "user.email", ME)
        git(clone, "checkout", "-q", "-b", "x;touch$(pwned)", "--track", "origin/x;touch$(pwned)")
        code, out = run(clone)
        cmd = next(ln for ln in out.splitlines() if "pwned" in ln).split(": ", 1)[1]
        args = shlex.split(cmd)
        self.assertEqual(cmd, shlex.join(args))
        self.assertEqual(args[:2], ["git", "push"])
        self.assertIn("x;touch$(pwned):x;touch$(pwned)", args)

    def test_not_a_repo_exits_2(self):
        code, out = run(tree(self))
        self.assertEqual(code, 2)
        self.assertIn("not a git repository", out)

    def test_message_transform(self):
        self.assertEqual(watermark.clean_message(f"x\n\n{CODEX}\nCo-authored-by: Ana <a@b.c>\n".encode()),
                         b"x\n\nCo-authored-by: Ana <a@b.c>\n")
        self.assertEqual(watermark.clean_message(b"x\n\nClaude-Session: abc\n"), b"x\n")
        self.assertEqual(watermark.clean_message(b"plain\n"), b"plain\n")


    def test_invisible_only_history_is_found_rewritten_and_verified(self):
        repo = new_repo(self)
        commit(repo, "one\n", ME, {"a.txt": "1\n"}, 1_700_000_000)
        dirty = commit(repo, "two\u200b with\u00a0nbsp\u202e\n", ME, {"a.txt": "2\n"}, 1_700_000_100)
        before = history(repo)
        code, out = run(repo, dry_run=True)
        self.assertIn(dirty[:10], out)
        self.assertEqual(history(repo), before)
        code, out = run(repo)
        self.assertEqual(code, 0, out)
        after = history(repo)
        self.assertEqual([r[:3] for r in after], [r[:3] for r in before])
        self.assertEqual(after[0][3], "two with nbsp")
        self.assertEqual(git(repo, "cat-file", "commit", "main").encode().count(b"\xe2\x80"), 0)
        code, out = run(repo)
        self.assertIn("clean", out)


class RewriteRange(unittest.TestCase):
    def setUp(self):
        self.repo = new_repo(self)
        self.one = commit(self.repo, "one\n", ME, {"a.txt": "1\n"}, 1_700_000_000)
        self.dirty = commit(self.repo, f"two\n\n{CODEX}\n", ME, {"a.txt": "2\n"}, 1_700_000_100)
        commit(self.repo, f"three\n\n{CLAUDE}\n", ME, {"b.txt": "3\n"}, 1_700_000_200)
        commit(self.repo, "four\n", ME, {"c.txt": "4\n"}, 1_700_000_300)
        git(self.repo, "tag", "light", self.dirty)

    def test_rewrite_range_keeps_trees_and_dates_and_writes_a_backup(self):
        before = history(self.repo)
        old_tip = git(self.repo, "rev-parse", "main")
        changed, bundle = scrub.rewrite_range(self.repo, "refs/heads/main", self.one, {ME})
        self.assertEqual(changed, 2)
        after = history(self.repo)
        self.assertEqual([r[:3] for r in after], [r[:3] for r in before])
        self.assertEqual((after[2][3], after[1][3], after[0][3]), ("two", "three", "four"))
        self.assertEqual(git(self.repo, "rev-parse", "main~3"), self.one)
        self.assertEqual(git(self.repo, "rev-parse", "light"), self.dirty)
        self.assertTrue(bundle.is_file())
        self.assertIn(old_tip, git(self.repo, "bundle", "list-heads", str(bundle)))

    def test_a_range_with_another_author_or_a_signature_is_refused(self):
        tip = commit(self.repo, "five\n", OTHER, {"d.txt": "5\n"}, 1_700_000_400)
        with self.assertRaisesRegex(scrub.Abort, "someone else"):
            scrub.rewrite_range(self.repo, "refs/heads/main", self.one, {ME})
        self.assertEqual(git(self.repo, "rev-parse", "main"), tip)
        self.assertEqual(scrub.rewrite_range(self.repo, "refs/heads/main", self.one, {ME, OTHER})[0], 2)

    def test_backups_go_to_the_common_git_dir_from_a_linked_worktree(self):
        git(self.repo, "branch", "side")
        wt = self.repo.parent / "wt"
        git(self.repo, "worktree", "add", "-q", str(wt), "side")
        _, bundle = scrub.rewrite_range(wt, "refs/heads/side", self.one, {ME})
        self.assertEqual(bundle.parent, Path(git(self.repo, "rev-parse", "--absolute-git-dir")))
        git(self.repo, "worktree", "remove", str(wt))
        self.assertTrue(bundle.is_file())

    def test_without_a_base_only_commits_off_every_remote_are_rewritten(self):
        origin = self.repo.parent / "origin.git"
        git(self.repo.parent, "init", "-q", "--bare", str(origin))
        git(self.repo, "remote", "add", "origin", str(origin))
        git(self.repo, "push", "-q", "origin", f"{self.dirty}:refs/heads/old")
        self.assertEqual(scrub.rewrite_range(self.repo, "refs/heads/main", None, {ME})[0], 1)
        self.assertEqual(git(self.repo, "rev-parse", "main~2"), self.dirty)
        self.assertEqual(git(self.repo, "log", "-1", "--format=%B", "main~1"), "three")

    def test_a_bad_range_rewrite_restores_the_branch(self):
        from unittest import mock
        tip = git(self.repo, "rev-parse", "main")
        real = scrub.rewrite_stream
        def tamper(stream, emails):
            out, marks = real(stream, emails)
            return out.replace(b"four", b"fowr"), marks
        with mock.patch.object(scrub, "rewrite_stream", tamper):
            with self.assertRaises(scrub.Abort):
                scrub.rewrite_range(self.repo, "refs/heads/main", self.one, {ME})
        self.assertEqual(git(self.repo, "rev-parse", "main"), tip)


class CleanMessage(unittest.TestCase):
    def test_trailers_per_tool(self):
        lines = [
            "Co-authored-by: Claude <noreply@anthropic.com>",
            "Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>",
            "Co-authored-by: copilot-swe-agent[bot] <x@users.noreply.github.com>",
            "Co-authored-by: google-labs-jules[bot] <x@y>",
            "Co-authored-by: jules[bot] <x@y>",
            "Co-authored-by: devin-ai-integration[bot] <x@y>",
            "Co-authored-by: Gemini <x@y>",
            "Co-authored-by: Cursor Agent <cursoragent@cursor.com>",
            "Co-authored-by: Jules <x@y>",
            "Generated with [Claude Code](https://claude.com/claude-code)",
            "Generated by Copilot",
            "Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>",
            "Co-authored-by: Codex <noreply@openai.com>",
            "Co-authored-by: ChatGPT <x@y.z>",
            "Co-authored-by: Gemini <gemini@google.com>",
            "Co-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
            "Co-authored-by: Antigravity <x@y.z>",
            "Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>",
            "Co-authored-by: GitHub Copilot <x@y.z>",
            "Co-authored-by: Cursor Agent <cursoragent@cursor.com>",
            "Co-authored-by: Someone <cursoragent@cursor.com>",
            "Co-authored-by: Devin AI <devin-ai-integration[bot]@users.noreply.github.com>",
            "Co-authored-by: aider (gpt-4) <aider@aider.chat>",
            "Co-authored-by: an AI <x@y.z>",
            "Co-authored-by: Bot <noreply@anthropic.com>",
            "Co-authored-by: Bot <noreply@openai.com>",
            "Generated with Claude Code",
            "Generated with [Codex](https://openai.com/codex/)",
            "Generated by Gemini",
            "Generated with GitHub Copilot",
            "Generated by Cursor",
            "Generated with Antigravity",
            "Made with Cursor",
            "Claude-Session: abc",
            "\U0001f916 Generated by a tool",
            "AI-assisted: yes",
            "ai-generated",
        ]
        for line in lines:
            with self.subTest(line=line):
                self.assertEqual(watermark.clean_message(f"x\n\n{line}\n".encode()), b"x\n")
                self.assertTrue(watermark.has_watermark(f"x\n\n{line}\n".encode()))

    def test_humans_and_prose_survive(self):
        for text in ["Co-authored-by: Ana Souza <ana@example.com>", "Co-authored-by: Jules Verne <jv@example.com>",
                     "Co-authored-by: Devin Smith <devin@example.com>",
                     "Co-authored-by: Devin Smith <devin@gmail.com>",
                     "Co-authored-by: Claude Monet <claude@example.com>",
                     "Co-authored-by: Claude Debussy <cd@gmail.com>",
                     "Co-authored-by: Gemini Ortiz <go@example.com>",
                     "Co-authored-by: Aider Kim <ak@example.com>",
                     "Co-authored-by: Cursor Lee <cl@example.com>",
                     "Co-authored-by: Anthropic Ng <an@example.com>",
                     "Co-authored-by: Pat Doe <pat@openai-fans.org>",
                     "Generated with the cursor position helper",
                     "Generated by hand with copilot-style snippets",
                     "fix the cursor position after paste", "Reviewed the generated output", "Made with care"]:
            with self.subTest(text=text):
                msg = f"x\n\n{text}\n".encode()
                self.assertEqual(watermark.clean_message(msg), msg)
                self.assertFalse(watermark.has_watermark(msg))

    def test_invisible_characters(self):
        self.assertEqual(watermark.clean_message("a\u200bb\u00a0c\u202fd\u202ee\ufefff\u00adg\n".encode()), b"ab c defg\n")

    def test_idempotent_and_byte_identical_when_clean(self):
        dirty = f"x\u200b\n\n{CODEX}\n\n\n".encode()
        once = watermark.clean_message(dirty)
        self.assertEqual(once, b"x\n")
        self.assertEqual(watermark.clean_message(once), once)
        clean = b"plain\n\n\n"
        self.assertIs(watermark.clean_message(clean), clean)

    def test_not_utf8_still_loses_attribution(self):
        self.assertEqual(watermark.clean_message(b"caf\xe9\n\nClaude-Session: a\n"), b"caf\xe9\n")


if __name__ == "__main__":
    unittest.main()
