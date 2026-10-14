import shutil
import unittest
from pathlib import Path

from harness import collect
from tests.util import tree, write

FIX = Path(__file__).parent / "fixtures" / "rollouts"


def home_with(root, names, sub="sessions/2026/10/10"):
    home = root / "codex home"
    for n in names:
        dst = home / sub / f"rollout-2026-10-10T10-00-00-{n}.jsonl"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIX / f"{n}.jsonl", dst)
    return home


def totals(con, thread):
    return con.execute("SELECT SUM(input), SUM(cached), SUM(output) FROM turn_usage WHERE thread_id=?", (thread,)).fetchone()


class Scan(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.home = home_with(self.root, ["main", "guardian", "subagent", "legacy", "bad"])
        self.con = collect.connect(collect.db_path(self.home))
        self.addCleanup(self.con.close)

    def test_records_win_over_token_count(self):
        collect.scan(self.con, self.home)
        self.assertEqual(totals(self.con, "main-1"), (6000, 4300, 160))

    def test_legacy_uses_last_usage_and_skips_duplicates(self):
        collect.scan(self.con, self.home)
        self.assertEqual(totals(self.con, "old-1"), (230, 100, 70))

    def test_kinds_and_parents(self):
        collect.scan(self.con, self.home)
        rows = dict(self.con.execute("SELECT id, kind || ':' || COALESCE(parent_id, '') FROM threads"))
        self.assertEqual(rows["main-1"], "main:")
        self.assertEqual(rows["g-1"], "guardian:main-1")
        self.assertEqual(rows["sub-1"], "subagent:main-1")

    def test_model_follows_turn_context(self):
        collect.scan(self.con, self.home)
        models = dict(self.con.execute("SELECT key, model FROM turn_usage WHERE thread_id='main-1'"))
        self.assertEqual(models, {"r1": "m-a", "r2": "m-a", "r3": "m-b"})

    def test_calls_compactions(self):
        collect.scan(self.con, self.home)
        calls = self.con.execute("SELECT call_id, cmd, escalated, turn_id FROM calls ORDER BY call_id").fetchall()
        self.assertEqual(calls, [("c1", "git status", 0, "t1"), ("c2", "curl -sI https://example.com", 1, "t2"), ("c3", "sleep 30", 0, "t3")])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM compactions").fetchone()[0], 1)

    def test_quarantine_keeps_going(self):
        summary = collect.scan(self.con, self.home)
        self.assertEqual(summary["quarantined"], 2)
        self.assertEqual(totals(self.con, "bad-1"), (10, 0, 1))
        reasons = [r for (r,) in self.con.execute("SELECT reason FROM quarantine ORDER BY line")]
        self.assertEqual(reasons, ["not JSON", "token_usage_record shape"])

    def test_idempotent_rescan_and_archive_move(self):
        collect.scan(self.con, self.home)
        collect.scan(self.con, self.home, rescan=True)
        src = next((self.home / "sessions").rglob("*-main.jsonl"))
        (self.home / "archived_sessions").mkdir()
        src.rename(self.home / "archived_sessions" / src.name)
        collect.scan(self.con, self.home)
        self.assertEqual(totals(self.con, "main-1"), (6000, 4300, 160))

    def test_partial_last_line_waits(self):
        home = home_with(self.root / "p", [])
        f = home / "sessions" / "rollout-x.jsonl"
        lines = (FIX / "subagent.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
        write(f, lines[0] + lines[1] + lines[2].rstrip("\n")[:40])
        con = collect.connect(collect.db_path(home))
        self.addCleanup(con.close)
        collect.scan(con, home)
        self.assertEqual(totals(con, "sub-1"), (None, None, None))
        write(f, "".join(lines))
        collect.scan(con, home)
        self.assertEqual(totals(con, "sub-1"), (500, 0, 5))

    def test_appended_lines_are_read_incrementally(self):
        home = home_with(self.root / "a", [])
        f = home / "sessions" / "rollout-y.jsonl"
        lines = (FIX / "main.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
        write(f, "".join(lines[:5]))
        con = collect.connect(collect.db_path(home))
        self.addCleanup(con.close)
        collect.scan(con, home)
        write(f, "".join(lines))
        collect.scan(con, home)
        self.assertEqual(totals(con, "main-1"), (6000, 4300, 160))


class ToolCall(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(collect.tool_call({"type": "function_call", "call_id": "a", "arguments": '{"command": ["git", "push"], "sandbox_permissions": "require_escalated"}'}), ("a", "git push", True))
        self.assertIsNone(collect.tool_call({"type": "function_call", "call_id": "a", "arguments": "{bad"}))
        self.assertIsNone(collect.tool_call({"type": "custom_tool_call", "call_id": "a", "input": "text(await tools.view_image({path:\"x\"}))"}))
        self.assertEqual(collect.tool_call({"type": "custom_tool_call", "call_id": "b", "input": 'tools.exec_command({cmd:"echo \\"hi\\""})'}), ("b", 'echo "hi"', False))
        self.assertIsNone(collect.tool_call({"type": "message"}))


class Robustness(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def scan(self, names):
        home = home_with(self.root / names[0], names)
        con = collect.connect(collect.db_path(home))
        self.addCleanup(con.close)
        return con, collect.scan(con, home)

    def test_fork_keeps_first_session_meta(self):
        con, _ = self.scan(["forked"])
        self.assertEqual(totals(con, "fork-1"), (7, 0, 1))
        self.assertEqual(totals(con, "main-1"), (None, None, None))
        self.assertEqual(con.execute("SELECT kind FROM threads WHERE id='fork-1'").fetchone()[0], "subagent")

    def test_poison_lines_are_quarantined_and_later_files_still_collected(self):
        con, summary = self.scan(["poison", "subagent"])
        self.assertEqual(totals(con, "poison-1"), (5, 0, 1))
        self.assertEqual(totals(con, "sub-1"), (500, 0, 5))
        self.assertGreaterEqual(summary["quarantined"], 2)
