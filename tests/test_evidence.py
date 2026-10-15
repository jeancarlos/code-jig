import os
import shutil
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from harness import collect, evidence
from harness.analyze import Finding
from harness.evidence import Commit, group_stats, in_window, is_test, parse_log, reworked
from tests.util import tree, write

T0 = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)


def c(sha, days, subject="change", body="", hunks=None):
    return Commit(sha, T0 + timedelta(days=days), subject, body, hunks or {})


class TestCommands(unittest.TestCase):
    def test_is_test(self):
        for cmd in ("pytest -q", "python -m unittest discover", "dotnet test", "npm test", "pnpm test", "yarn test",
                    "npm run test -- --ci", "npx vitest run", "npx jest"):
            with self.subTest(cmd=cmd):
                self.assertTrue(is_test(cmd))
        for cmd in ("git status", "npm install", "dotnet build", "ls tests"):
            with self.subTest(cmd=cmd):
                self.assertFalse(is_test(cmd))


class Windows(unittest.TestCase):
    def test_inside_grace_and_outside(self):
        w = [(T0, T0 + timedelta(hours=1))]
        self.assertTrue(in_window(T0 + timedelta(minutes=30), w))
        self.assertTrue(in_window(T0 + timedelta(hours=2, minutes=59), w))
        self.assertFalse(in_window(T0 + timedelta(hours=3, minutes=1), w))
        self.assertFalse(in_window(T0 - timedelta(minutes=1), w))
        self.assertFalse(in_window(T0, []))


class ParseLog(unittest.TestCase):
    def test_parse_log_hunks_and_fields(self):
        text = ("\x01aaa\x002026-03-01T10:00:00+00:00\x00add\x00body line\n\x00\n"
                "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,0 +1,3 @@\n+a\n+b\n+c\n@@ -9 +12 @@\n-o\n+n\n"
                "\x01bbb\x002026-03-02T10:00:00-03:00\x00second\x00\x00")
        a, b = parse_log(text)
        self.assertEqual((a.sha, a.subject, a.body.strip()), ("aaa", "add", "body line"))
        self.assertEqual(a.hunks, {"x.py": [(1, 0, 1, 3), (9, 1, 12, 1)]})
        self.assertEqual(b.when, datetime(2026, 3, 2, 13, 0, tzinfo=timezone.utc))
        self.assertEqual(b.hunks, {})

    def test_parse_log_binary_and_deleted_files(self):
        text = ("\x01ccc\x002026-03-01T10:00:00+00:00\x00mixed\x00\x00\n"
                "diff --git a/img.png b/img.png\nindex 1..2 100644\nBinary files a/img.png and b/img.png differ\n"
                "diff --git a/gone.py b/gone.py\ndeleted file mode 100644\n--- a/gone.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-x\n-y\n")
        [commit] = parse_log(text)
        self.assertEqual(commit.hunks, {"gone.py": [(1, 2, 0, 0)]})

    def test_parse_log_content_that_looks_like_headers(self):
        text = ("\x01ddd\x002026-03-01T10:00:00+00:00\x00sql\x00\x00\n"
                "diff --git a/q.sql b/q.sql\n--- a/q.sql\n+++ b/q.sql\n@@ -3 +3 @@\n--- old comment\n+++ new comment\n@@ -9,0 +10 @@\n+x\n")
        [commit] = parse_log(text)
        self.assertEqual(commit.hunks, {"q.sql": [(3, 1, 3, 1), (9, 0, 10, 1)]})

    def test_parse_log_empty(self):
        self.assertEqual(parse_log(""), [])


class Rework(unittest.TestCase):
    def test_same_lines_within_14_days(self):
        target = c("t", 0, hunks={"x.py": [(0, 0, 10, 5)]})
        later = c("l", 5, hunks={"x.py": [(12, 1, 12, 1)]})
        self.assertTrue(reworked(target, [later, target]))

    def test_other_lines_or_other_file_or_too_late(self):
        target = c("t", 0, hunks={"x.py": [(0, 0, 10, 5)]})
        self.assertFalse(reworked(target, [c("a", 5, hunks={"x.py": [(20, 2, 20, 2)]})]))
        self.assertFalse(reworked(target, [c("b", 5, hunks={"y.py": [(12, 1, 12, 1)]})]))
        self.assertFalse(reworked(target, [c("d", 15, hunks={"x.py": [(12, 1, 12, 1)]})]))
        self.assertFalse(reworked(target, [c("e", 5, hunks={"x.py": [(12, 0, 13, 4)]})]))

    def test_revert_fixup_squash(self):
        target = c("abc123", 0, subject="add parser")
        self.assertTrue(reworked(target, [c("r", 1, 'Revert "add parser"', "This reverts commit abc123.")]))
        self.assertTrue(reworked(target, [c("f", 1, "fixup! add parser")]))
        self.assertTrue(reworked(target, [c("s", 1, "squash! add parser")]))
        self.assertFalse(reworked(target, [c("o", 1, "add parser tests")]))

    def test_earlier_commits_never_count(self):
        target = c("t", 3, hunks={"x.py": [(0, 0, 10, 5)]})
        self.assertFalse(reworked(target, [c("early", 1, hunks={"x.py": [(12, 1, 12, 1)]})]))


class Groups(unittest.TestCase):
    def test_young_commits_are_not_mature(self):
        now = T0 + timedelta(days=20)
        group = [c("old", 0), c("young", 10)]
        stats = group_stats(group, group, now)
        self.assertEqual((stats["commits"], stats["mature"]), (2, 1))

    def test_insufficient_below_twenty(self):
        now = T0 + timedelta(days=100)
        group = [c(f"s{i}", 0) for i in range(19)]
        self.assertIsNone(group_stats(group, group, now)["rework_rate"])
        group.append(c("s19", 0))
        self.assertEqual(group_stats(group, group, now)["rework_rate"], 0.0)

    def test_rate(self):
        self.assertEqual(evidence.rate(30, 25, 5), {"commits": 30, "mature": 25, "reworked": 5, "rework_rate": 0.2})
        self.assertIsNone(evidence.rate(5, 5, 1)["rework_rate"])


GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(root, *args, date=None):
    env = {**os.environ, **GIT_ENV}
    if date:
        env |= {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def commit(root, name, text, date, msg="change"):
    write(root / name, text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", msg, date=date)


def new_repo(test):
    root = tree(test) / "repo"
    root.mkdir()
    git(root, "init", "-q")
    return root


def db(test, sessions=(), calls=(), usage=(), guardian=()):
    con = collect.connect(tree(test) / "usage.sqlite3")
    test.addCleanup(con.close)
    for tid, kind, parent, started, cwd in sessions:
        con.execute("INSERT INTO threads VALUES (?,?,?,?,?)", (tid, parent, kind, started, cwd))
    for tid, cid, ts, cmd, esc, code, skill in calls:
        con.execute("INSERT INTO calls (thread_id, call_id, turn_id, ts, cmd, escalated, exit_code, skill) VALUES (?,?,NULL,?,?,?,?,?)",
                    (tid, cid, ts, cmd, esc, code, skill))
    for tid, key, ts, inp, cached, out in usage:
        con.execute("INSERT INTO usage VALUES (?,?,NULL,?,NULL,?,?,?,0)", (tid, key, ts, inp, cached, out))
    for tid, line, ts, outcome in guardian:
        con.execute("INSERT INTO guardian VALUES (?,?,?,?)", (tid, line, ts, outcome))
    con.commit()
    return con


@unittest.skipIf(shutil.which("git") is None, "git not installed")
class GitRepos(unittest.TestCase):
    def test_split_by_session_window(self):
        root = new_repo(self)
        (root / "sub").mkdir()
        commit(root, "a.py", "1\n", "2026-01-01T10:00:00Z", "before")
        commit(root, "a.py", "2\n", "2026-03-01T10:30:00Z", "inside")
        commit(root, "a.py", "3\n", "2026-03-01T12:30:00Z", "grace")
        commit(root, "a.py", "4\n", "2026-03-01T14:00:00Z", "after")
        con = db(self, sessions=[("s1", "main", None, "2026-03-01T10:00:00Z", str(root / "sub"))],
                 usage=[("s1", "r1", "2026-03-01T11:00:00Z", 100, 50, 10)])
        now = T0 + timedelta(days=200)
        data = evidence.report(con, datetime(2025, 12, 1, tzinfo=timezone.utc), now)
        [repo] = data["repos"]
        self.assertEqual(Path(repo["root"]), root.resolve())
        self.assertEqual((repo["harness"]["commits"], repo["baseline"]["commits"]), (2, 2))

    def test_offset_commit_dates_compare_as_instants(self):
        root = new_repo(self)
        commit(root, "a.py", "1\n", "2026-03-01T07:30:00-03:00")
        con = db(self, sessions=[("s1", "main", None, "2026-03-01T10:00:00Z", str(root))],
                 usage=[("s1", "r1", "2026-03-01T11:00:00Z", 1, 0, 1)])
        data = evidence.report(con, datetime(2026, 2, 1, tzinfo=timezone.utc), T0 + timedelta(days=30))
        self.assertEqual(data["repos"][0]["harness"]["commits"], 1)

    def test_non_ascii_paths_in_hunks(self):
        root = new_repo(self)
        commit(root, "dir with space/ação.py", "x = 1\n", "2026-03-01T10:00:00Z")
        [c0] = evidence.git_log(root, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(list(c0.hunks), ["dir with space/ação.py"])

    def test_rework_through_real_git(self):
        root = new_repo(self)
        commit(root, "a.py", "1\n2\n3\n", "2026-03-01T10:00:00Z", "add a")
        commit(root, "a.py", "1\nTWO\n3\n", "2026-03-05T10:00:00Z", "tweak")
        commit(root, "b.py", "b\n", "2026-03-06T10:00:00Z", "add b")
        git(root, "revert", "--no-edit", "HEAD", date="2026-03-07T10:00:00Z")
        every = evidence.git_log(root, datetime(2026, 1, 1, tzinfo=timezone.utc))
        by = {c0.subject: c0 for c0 in every}
        self.assertTrue(evidence.reworked(by["add a"], every))
        self.assertTrue(evidence.reworked(by["add b"], every))
        self.assertFalse(evidence.reworked(by["tweak"], every))

    def test_missing_cwd_and_empty_repo(self):
        empty = new_repo(self)
        con = db(self, sessions=[("gone", "main", None, "2026-03-01T10:00:00Z", str(empty.parent / "deleted")),
                                 ("plain", "main", None, "2026-03-01T10:00:00Z", str(tree(self))),
                                 ("empty", "main", None, "2026-03-01T10:00:00Z", str(empty)),
                                 ("none", "main", None, "2026-03-01T10:00:00Z", None)])
        data = evidence.report(con, datetime(2026, 2, 1, tzinfo=timezone.utc), T0)
        self.assertEqual(len(data["unreachable"]), 3)
        self.assertEqual(data["repos"][0]["harness"]["commits"], 0)

    def test_repo_filter(self):
        root = new_repo(self)
        commit(root, "a.py", "1\n", "2026-03-01T10:00:00Z")
        con = db(self)
        data = evidence.report(con, datetime(2026, 2, 1, tzinfo=timezone.utc), T0, repo=root)
        self.assertEqual([r["baseline"]["commits"] for r in data["repos"]], [1])


class FromDatabase(unittest.TestCase):
    def setUp(self):
        self.con = db(self,
                      sessions=[("s1", "main", None, "2026-03-01T10:00:00Z", None), ("sub", "subagent", "s1", "2026-03-01T10:05:00Z", None),
                                ("s2", "main", None, "2026-03-02T10:00:00Z", None), ("g", "guardian", "s1", "2026-03-01T10:06:00Z", None)],
                      calls=[("s1", "c1", "2026-03-01T10:01:00Z", "python -m unittest", 0, 0, None),
                             ("sub", "c2", "2026-03-01T10:06:00Z", "pytest -q", 0, 1, None),
                             ("s1", "c3", "2026-03-01T10:07:00Z", "cat x/skills/bug-hunt/SKILL.md", 0, 0, "bug-hunt"),
                             ("s2", "c4", "2026-03-02T10:01:00Z", "curl -sI https://example.com", 1, 0, None),
                             ("s2", "c5", "2026-03-02T10:02:00Z", "cat y/skills/bug-hunt/SKILL.md", 0, 0, "bug-hunt")],
                      usage=[("s1", "r1", "2026-03-01T10:30:00Z", 1000, 900, 100), ("sub", "r2", "2026-03-01T10:20:00Z", 500, 400, 50),
                             ("g", "r3", "2026-03-01T10:06:30Z", 300, 0, 10), ("s2", "r4", "2026-03-02T10:10:00Z", 200, 100, 20)],
                      guardian=[("g", 3, "2026-03-01T10:06:40Z", "allow")])
        self.since = "2026-02-01T00:00:00Z"

    def test_sessions_span_children(self):
        sess = {s.id: s for s in evidence.sessions(self.con, self.since)}
        self.assertEqual(set(sess), {"s1", "s2"})
        self.assertEqual(sess["s1"].end, datetime(2026, 3, 1, 10, 30, tzinfo=timezone.utc))

    def test_discipline_counts_subagent_runs_for_the_owner(self):
        self.assertEqual(evidence.discipline(self.con, {"s1", "s2"}),
                         {"sessions": 2, "with_tests": 1, "test_runs": 2, "passed": 1})

    def test_test_run_without_exit_code(self):
        self.con.execute("INSERT INTO calls (thread_id, call_id, ts, cmd, escalated) VALUES ('s2', 'c6', '2026-03-02T10:03:00Z', 'npm test', 0)")
        self.assertEqual(evidence.discipline(self.con, {"s1", "s2"}),
                         {"sessions": 2, "with_tests": 2, "test_runs": 2, "passed": 1})

    def test_use(self):
        u = evidence.use(self.con, self.since, ["bug-hunt", "codegen", "grilling"])
        self.assertEqual(u, {"skills": {"bug-hunt": 2}, "never": ["codegen", "grilling"], "guardian": {"allow": 1},
                             "calls": 5, "escalated": 1})

    def test_cost(self):
        sess = evidence.sessions(self.con, self.since)
        s1 = [s for s in sess if s.id == "s1"]
        k = evidence.cost(self.con, self.since, sess, s1, 2)
        self.assertEqual(k["tokens"], 1000 + 100 + 500 + 50 + 300 + 10 + 200 + 20)
        self.assertEqual(k["tokens_per_harness_commit"], (1000 + 100 + 500 + 50 + 300 + 10) / 2)
        self.assertAlmostEqual(k["cache_hit"], (900 + 400 + 0 + 100) / (1000 + 500 + 300 + 200))
        self.assertEqual(k["median_minutes"], 20.0)

    def test_installed_skills(self):
        root = tree(self)
        for name in ("b", "a"):
            write(root / name / "SKILL.md", "x\n")
        (root / "not-a-skill").mkdir()
        with mock.patch("harness.paths.agents_skills", return_value=root):
            self.assertEqual(evidence.installed_skills(), ["a", "b"])


class Quality(unittest.TestCase):
    def test_sample_is_even_and_bounded(self):
        group = [c(str(i), i) for i in range(10)]
        self.assertEqual([x.sha for x in evidence.sample(group, 3)], ["0", "3", "6"])
        self.assertEqual(len(evidence.sample(group, 50)), 10)
        self.assertEqual(evidence.sample(group, 0), [])

    def test_quality_counts_per_100_changed_lines(self):
        group = [c("a", 0, hunks={"x.py": [(0, 0, 1, 30)]}), c("b", 1, hunks={"y.py": [(0, 0, 1, 20)]})]
        found = {"a": [Finding("security", "ruff", "S1", "x.py", 1, "m")], "b": [Finding("complexity", "lizard", "c", "y.py", 1, "m")] * 2}
        q = evidence.quality(Path("."), group, 5, lambda root, commit: found[commit.sha])
        self.assertEqual(q, {"sampled": 2, "changed_lines": 50, "findings": {"security": 1, "complexity": 2},
                             "per_100_lines": {"security": 2.0, "complexity": 4.0}})
        self.assertIsNone(evidence.quality(Path("."), group, 0, None))

    @unittest.skipIf(shutil.which("git") is None, "git not installed")
    def test_analyze_commit_cleans_its_worktree(self):
        root = new_repo(self)
        write(root / "pyproject.toml", "[project]\nname='x'\n")
        commit(root, "a.py", "x = 1\n", "2026-03-01T10:00:00Z")
        [c0] = evidence.git_log(root, datetime(2026, 1, 1, tzinfo=timezone.utc))
        empty = tree(self)
        self.assertEqual(evidence.analyze_commit(root, c0, path=str(empty)), [])
        listed = subprocess.run(["git", "-C", str(root), "worktree", "list"], capture_output=True, text=True, encoding="utf-8").stdout
        self.assertEqual(len(listed.strip().splitlines()), 1)

    @unittest.skipIf(shutil.which("git") is None, "git not installed")
    def test_report_carries_quality_when_asked(self):
        root = new_repo(self)
        commit(root, "a.py", "1\n", "2026-03-01T10:30:00Z")
        con = db(self, sessions=[("s1", "main", None, "2026-03-01T10:00:00Z", str(root))],
                 usage=[("s1", "r1", "2026-03-01T11:00:00Z", 1, 0, 1)])
        runner = lambda r, commit: [Finding("bug", "ruff", "B1", "a.py", 1, "m")]
        data = evidence.report(con, datetime(2026, 2, 1, tzinfo=timezone.utc), T0 + timedelta(days=30), analyze_n=1, runner=runner)
        self.assertEqual(data["repos"][0]["harness"]["quality"]["findings"], {"bug": 1})
        self.assertEqual(data["totals"]["harness"]["quality"]["findings"], {"bug": 1})
        self.assertIsNone(evidence.report(con, datetime(2026, 2, 1, tzinfo=timezone.utc), T0)["repos"][0]["harness"]["quality"])
