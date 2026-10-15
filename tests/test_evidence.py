import unittest
from datetime import datetime, timedelta, timezone

from harness import evidence
from harness.evidence import Commit, group_stats, in_window, is_test, parse_log, reworked

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
