import json
import unittest

from harness import collect, paths
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
