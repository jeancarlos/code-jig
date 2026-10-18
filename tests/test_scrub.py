# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import os
import subprocess
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
                            capture_output=True, text=True, encoding="utf-8", check=False).stdout.strip()
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


def history(repo: Path) -> list[tuple[str, str, str, str]]:
    out = git(repo, "log", "--format=%T%x00%an <%ae> %ad%x00%cn <%ce> %cd%x00%B%x1e", "main")
    return [tuple(r.strip("\n").split("\0")) for r in out.split("\x1e") if r.strip()]


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

    def test_blocker_reads_the_range_in_one_batch(self):
        from unittest import mock
        with mock.patch.object(scrub, "_git", wraps=scrub._git) as calls:
            self.assertIsNone(scrub.blocker(self.repo, scrub.range_revs("refs/heads/main", None), {ME}))
        self.assertLessEqual(calls.call_count, 2)
        commit(self.repo, "five\n", OTHER, {"d.txt": "5\n"}, 1_700_000_400)
        self.assertIn("someone else", scrub.blocker(self.repo, scrub.range_revs("refs/heads/main", self.one), {ME}))

    def test_common_dir_from_a_subdirectory_without_path_format(self):
        sub = self.repo / "deep" / "er"
        sub.mkdir(parents=True)
        from unittest import mock
        with mock.patch.object(scrub, "_git", wraps=scrub._git) as calls:
            found = scrub.common_dir(sub)
        self.assertEqual(found, Path(git(self.repo, "rev-parse", "--absolute-git-dir")).resolve())
        self.assertFalse(any("--path-format=absolute" in c.args for c in calls.call_args_list))

    def test_backups_go_to_the_common_git_dir_from_a_linked_worktree(self):
        git(self.repo, "branch", "side")
        wt = self.repo.parent / "wt"
        git(self.repo, "worktree", "add", "-q", str(wt), "side")
        _, bundle = scrub.rewrite_range(wt, "refs/heads/side", self.one, {ME})
        self.assertEqual(bundle.parent, Path(git(self.repo, "rev-parse", "--absolute-git-dir")).resolve())
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
        with mock.patch.object(scrub, "rewrite_stream", tamper), self.assertRaises(scrub.Abort):
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

    def test_message_transform(self):
        self.assertEqual(watermark.clean_message(f"x\n\n{CODEX}\nCo-authored-by: Ana <a@b.c>\n".encode()),
                         b"x\n\nCo-authored-by: Ana <a@b.c>\n")
        self.assertEqual(watermark.clean_message(b"x\n\nClaude-Session: abc\n"), b"x\n")
        self.assertEqual(watermark.clean_message(b"plain\n"), b"plain\n")

    def test_a_subject_or_body_that_mentions_ai_generated_is_kept(self):
        for msg in ("AI-generated images are now rejected by the validator\n",
                    "fix: x\n\nAI-generated images are now rejected.\n",
                    "fix: x\n\nGenerated by Copilot, these stubs were rewritten by hand.\n\nMore text.\n"):
            with self.subTest(msg=msg):
                self.assertEqual(watermark.clean_message(msg.encode()), msg.encode())

    def test_non_ai_bot_co_authors_and_trailers_are_kept(self):
        for line in ("Co-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
                     "Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>",
                     "Signed-off-by: Ana <a@b.c>"):
            with self.subTest(line=line):
                msg = f"x\n\n{line}\n".encode()
                self.assertEqual(watermark.clean_message(msg), msg)

    def test_joiners_inside_emoji_and_words_are_kept(self):
        zwj, zwnj = chr(0x200D), chr(0x200C)
        family = chr(0x1F468) + zwj + chr(0x1F469) + zwj + chr(0x1F467)
        persian = chr(0x645) + chr(0x6CC) + zwnj + chr(0x62E) + chr(0x648) + chr(0x627) + chr(0x647) + chr(0x645)
        msg = f"docs: {family} {persian}\n".encode()
        self.assertEqual(watermark.clean_message(msg), msg)
        self.assertEqual(watermark.clean_message(f"a{zwj}b\n".encode()), b"ab\n")

    def test_a_verbose_commit_template_keeps_its_diff(self):
        msg = (f"fix\n\n{CODEX}\n# Please enter the commit message for your changes.\n#\n"
               "# ------------------------ >8 ------------------------\n# Do not modify or remove the line above.\n"
               f"diff --git a/x b/x\nCo-authored-by: Codex <noreply@openai.com>\n")
        self.assertEqual(watermark.clean_message(msg.encode()),
                         msg.replace(f"fix\n\n{CODEX}\n", "fix\n\n", 1).encode())


if __name__ == "__main__":
    unittest.main()
