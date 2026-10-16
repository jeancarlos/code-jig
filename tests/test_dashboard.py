import json
import unittest

from codejig import collect, evidence, paths
from tests.test_collect import home_with
from tests.util import tree


class Dashboard(unittest.TestCase):
    def test_every_query_runs(self):
        home = home_with(tree(self), ["main", "guardian", "subagent", "legacy"])
        con = collect.connect(collect.db_path(home))
        self.addCleanup(con.close)
        collect.scan(con, home)
        board = json.loads((paths.CORE / "dashboard.json").read_text(encoding="utf-8"))
        queries = [t["queryText"] for p in board["panels"] for t in p.get("targets", [])]
        self.assertGreaterEqual(len(queries), 4)
        results = [con.execute(q.replace("$__from", "0").replace("$__to", "4102444800000")).fetchall() for q in queries]
        self.assertAlmostEqual(results[0][0][0], 100.0 * 7000 / 13730)
        self.assertEqual(results[1][0][0], 7000)

    def test_evidence_panels(self):
        home = home_with(tree(self), ["main", "guardian", "tools"])
        con = collect.connect(collect.db_path(home))
        self.addCleanup(con.close)
        collect.scan(con, home)
        board = json.loads((paths.CORE / "dashboard.json").read_text(encoding="utf-8"))
        queries = {p["title"]: p["targets"][0]["queryText"] for p in board["panels"]}
        run = lambda title: con.execute(queries[title].replace("$__from", "0").replace("$__to", "4102444800000")).fetchall()
        self.assertEqual(run("Skill use (sessions)"), [("bug-hunt", 1), ("code-analysis", 1), ("grilling", 1), ("regression-tests", 1), ("using-superpowers", 1)])
        self.assertEqual(run("Test pass rate (%)"), [(50.0,)])
        self.assertEqual(run("Guardian outcomes"), [("allow", 1)])
        for marker in evidence.TEST_MARKERS:
            with self.subTest(marker=marker):
                self.assertIn(f"'%{marker}%'", queries["Test pass rate (%)"])
