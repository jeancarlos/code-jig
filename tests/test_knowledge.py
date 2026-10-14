import unittest

from harness.doctor import check_knowledge, check_superpowers
from harness.install import render_agents
from harness.overlay import Overlay
from tests.util import tree, write


class Knowledge(unittest.TestCase):
    def setUp(self):
        root = tree(self)
        self.core = root / "core-repo"
        write(self.core / "core" / "AGENTS.core.md", "core\n")
        self.ov = Overlay(root / "overlay", "v0.4.0", True)
        self.ov.root.mkdir(parents=True)

    def test_pointer_only_with_index(self):
        self.assertNotIn("## Knowledge", render_agents(self.core, self.ov.root))
        write(self.ov.root / "knowledge" / "INDEX.md", "- [a](a.md)\n")
        text = render_agents(self.core, self.ov.root)
        self.assertIn("## Knowledge", text)
        self.assertIn(str(self.ov.root / "knowledge" / "INDEX.md"), text)

    def test_index_cap(self):
        self.assertEqual(check_knowledge(self.ov)[0][0], "ok")
        (self.ov.root / "knowledge").mkdir()
        self.assertEqual(check_knowledge(self.ov)[0][0], "warn")
        write(self.ov.root / "knowledge" / "INDEX.md", "- x\n" * 150)
        self.assertEqual(check_knowledge(self.ov)[0][0], "ok")
        write(self.ov.root / "knowledge" / "INDEX.md", "- x\n" * 151)
        self.assertEqual(check_knowledge(self.ov)[0][0], "warn")

    def test_superpowers(self):
        home = tree(self)
        self.assertIn("codex plugin add superpowers@openai-curated-remote", check_superpowers(home)[0][2])
        write(home / "config.toml", '[plugins."superpowers@openai-curated"]\nenabled = true\n')
        self.assertEqual(check_superpowers(home)[0][0], "ok")


class RemotePlugin(unittest.TestCase):
    def test_remote_marketplace_install_is_found_in_the_plugin_cache(self):
        home = tree(self)
        (home / "plugins" / "cache" / "openai-curated-remote" / "superpowers" / "6.4.2").mkdir(parents=True)
        self.assertEqual(check_superpowers(home)[0][0], "ok")
