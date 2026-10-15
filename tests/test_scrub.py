import contextlib
import io
import os
import subprocess
import types
import unittest
from pathlib import Path

from harness import scrub
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
                            capture_output=True, text=True).stdout.strip()
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
        self.assertTrue(list(Path(git(self.repo, "rev-parse", "--absolute-git-dir")).glob("codex-harness-scrub-*.bundle")))

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

    def test_not_a_repo_exits_2(self):
        code, out = run(tree(self))
        self.assertEqual(code, 2)
        self.assertIn("not a git repository", out)

    def test_message_transform(self):
        self.assertEqual(scrub.scrub_message(f"x\n\n{CODEX}\nCo-authored-by: Ana <a@b.c>\n".encode()),
                         b"x\n\nCo-authored-by: Ana <a@b.c>\n")
        self.assertEqual(scrub.scrub_message(b"x\n\nClaude-Session: abc\n"), b"x\n")
        self.assertEqual(scrub.scrub_message(b"plain\n"), b"plain\n")


if __name__ == "__main__":
    unittest.main()
