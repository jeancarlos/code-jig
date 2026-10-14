import unittest

from harness import collect, tokens
from tests.test_collect import home_with
from tests.util import tree


class Summary(unittest.TestCase):
    def setUp(self):
        home = home_with(tree(self), ["main", "guardian", "subagent", "legacy", "bad"])
        self.con = collect.connect(collect.db_path(home))
        self.addCleanup(self.con.close)
        collect.scan(self.con, home)
        self.s = tokens.summary(self.con, "2026-10-01T00:00:00Z")

    def test_totals_and_guardian(self):
        self.assertEqual((self.s["input"], self.s["cached"], self.s["output"]), (13740, 10400, 336))
        self.assertEqual(self.s["by_kind"], {"main": 6240, "guardian": 7000, "subagent": 500})
        self.assertAlmostEqual(self.s["guardian_share"], 7000 / 13740)
        self.assertEqual((self.s["reviews"], self.s["input_per_review"]), (1, 7000))

    def test_escalations_and_sessions(self):
        self.assertEqual(self.s["escalations"], [("curl", 1)])
        top = self.s["sessions"][0]
        self.assertEqual(top, {"id": "main-1", "turns": 3, "input": 6000, "cached": 4300, "guardian_input": 7000,
                               "subagent_input": 500, "compactions": 1, "polling": 1})
        self.assertEqual(self.s["over_long"], 0)
        self.assertEqual(tokens.summary(self.con, "2026-10-01T00:00:00Z", long_turns=2)["over_long"], 1)

    def test_long_sessions_count_model_requests_not_user_turns(self):
        self.assertEqual(tokens.summary(self.con, "2026-10-01T00:00:00Z", long_turns=1)["over_long"], 2)

    def test_models_and_quarantine(self):
        self.assertEqual(self.s["models"], [("codex-auto-review", 7000, 100), ("m-b", 3500, 15), ("m-a", 3230, 220), ("(unknown)", 10, 1)])
        self.assertEqual(self.s["quarantined"], 2)

    def test_window_excludes_old_rows(self):
        s = tokens.summary(self.con, "2026-10-11T00:00:00Z")
        self.assertEqual(s["input"], 240)

    def test_render_flags_low_cache(self):
        text = "\n".join(tokens.render(self.s, 97.5))
        self.assertIn("Guardian share of input: 50.9%", text)
        self.assertIn("LOW", text)
        self.assertIn("quarantined", text)

    def test_empty_db_renders(self):
        con = collect.connect(collect.db_path(tree(self) / "h"))
        self.addCleanup(con.close)
        self.assertTrue(tokens.render(tokens.summary(con, "2026-10-01T00:00:00Z"), 97.5))


class Prefix(unittest.TestCase):
    def test_prefix(self):
        self.assertEqual(tokens.prefix("/usr/bin/git push origin main"), "git push")
        self.assertEqual(tokens.prefix("npm test -- --watch"), "npm test")
        self.assertEqual(tokens.prefix("curl -sI x"), "curl")
        self.assertEqual(tokens.prefix("FOO=1 make build"), "make")
        self.assertEqual(tokens.prefix(""), "")


class Escapes(unittest.TestCase):
    def test_control_characters_are_not_printed_raw(self):
        s = {"input": 1, "cached": 1, "output": 0, "by_kind": {}, "guardian_share": 0.0, "reviews": 0, "input_per_review": 0,
             "escalations": [("curl\x1b]52;c;cHduZWQ=\x07", 1)], "over_long": 0, "quarantined": 0,
             "sessions": [{"id": "s\x1b[2J", "turns": 1, "input": 1, "cached": 1, "guardian_input": 0, "subagent_input": 0, "compactions": 0, "polling": 0}],
             "models": [("m\x1b[31m", 1, 0)]}
        text = "\n".join(tokens.render(s, 97.5))
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x07", text)
