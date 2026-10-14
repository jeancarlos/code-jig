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


class BadCap(unittest.TestCase):
    def setUp(self):
        root = tree(self)
        self.home = root / "codex home"
        self.cwd = root
        self.cwd.mkdir(parents=True, exist_ok=True)

    def test_list_cap_falls_back_to_default(self):
        write(self.home / "config.toml", "project_doc_max_bytes = [1]\n")
        write(self.home / "AGENTS.md", "small")
        self.assertEqual(check_chain(self.home, self.cwd), [("ok", "AGENTS.md chain", "5 of 32768 bytes")])

    def test_bool_cap_falls_back_to_default(self):
        write(self.home / "config.toml", "project_doc_max_bytes = true\n")
        write(self.home / "AGENTS.md", "small")
        self.assertEqual(check_chain(self.home, self.cwd), [("ok", "AGENTS.md chain", "5 of 32768 bytes")])

    def test_non_utf8_config_falls_back_to_default(self):
        (self.home / "config.toml").parent.mkdir(parents=True, exist_ok=True)
        (self.home / "config.toml").write_bytes(b"\xff\xfe\x00bad")
        write(self.home / "AGENTS.md", "small")
        self.assertEqual(check_chain(self.home, self.cwd), [("ok", "AGENTS.md chain", "5 of 32768 bytes")])
