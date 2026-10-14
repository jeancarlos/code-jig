import unittest

from harness.doctor import DEFAULT_DOC_MAX, chain_files, check_chain
from tests.util import tree, write


class Chain(unittest.TestCase):
    def setUp(self):
        root = tree(self)
        self.home = root / "codex home"
        self.repo = root / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.cwd = self.repo / "pkg" / "sub"
        self.cwd.mkdir(parents=True)

    def test_order_and_override(self):
        g = write(self.home / "AGENTS.md", "g")
        r = write(self.repo / "AGENTS.md", "r")
        write(self.repo / "pkg" / "AGENTS.md", "plain")
        o = write(self.repo / "pkg" / "AGENTS.override.md", "override")
        self.assertEqual(chain_files(self.home, self.cwd), [g, r, o])

    def test_empty_global_override_falls_back(self):
        write(self.home / "AGENTS.override.md", "")
        g = write(self.home / "AGENTS.md", "g")
        self.assertEqual(chain_files(self.home, self.cwd), [g])

    def test_over_cap_fails(self):
        write(self.home / "AGENTS.md", "x" * (DEFAULT_DOC_MAX + 1))
        self.assertEqual(check_chain(self.home, self.cwd)[0][0], "FAIL")

    def test_custom_cap_from_config(self):
        write(self.home / "config.toml", "project_doc_max_bytes = 100\n")
        write(self.home / "AGENTS.md", "x" * 90)
        self.assertEqual(check_chain(self.home, self.cwd)[0][0], "warn")

    def test_under_cap_ok(self):
        write(self.home / "AGENTS.md", "small")
        self.assertEqual(check_chain(self.home, self.cwd)[0][0], "ok")
