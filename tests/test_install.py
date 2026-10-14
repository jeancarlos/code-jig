import unittest

from harness.install import MARKER, render_agents, run, write_generated
from harness.overlay import Overlay
from tests.util import tree, write


class Render(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.core = self.root / "core-repo"
        write(self.core / "core" / "AGENTS.core.md", "core rules\n")
        self.ov = self.root / "overlay"

    def test_core_then_overlay(self):
        write(self.ov / "AGENTS.overlay.md", "overlay rules\n")
        text = render_agents(self.core, self.ov)
        self.assertTrue(text.startswith(MARKER))
        self.assertLess(text.index("core rules"), text.index("overlay rules"))

    def test_overlay_file_optional(self):
        self.ov.mkdir(parents=True)
        self.assertEqual(render_agents(self.core, self.ov), MARKER + "core rules\n")


class WriteGenerated(unittest.TestCase):
    def setUp(self):
        self.home = tree(self) / "codex home"
        self.target = self.home / "AGENTS.md"

    def test_creates_new(self):
        self.assertIsNone(write_generated(self.target, MARKER + "x\n"))
        self.assertEqual(self.target.read_text(encoding="utf-8"), MARKER + "x\n")

    def test_overwrites_own_file_without_backup(self):
        write(self.target, MARKER + "old\n")
        self.assertIsNone(write_generated(self.target, MARKER + "new\n"))
        self.assertEqual(list(self.home.glob("AGENTS.md.bak-*")), [])

    def test_backs_up_user_file(self):
        write(self.target, "my own rules\n")
        backup = write_generated(self.target, MARKER + "new\n")
        self.assertEqual(backup.read_text(encoding="utf-8"), "my own rules\n")
        self.assertEqual(self.target.read_text(encoding="utf-8"), MARKER + "new\n")

    def test_bom_on_own_file_is_still_own(self):
        self.home.mkdir(parents=True)
        self.target.write_bytes(b"\xef\xbb\xbf" + (MARKER + "old\n").encode())
        self.assertIsNone(write_generated(self.target, MARKER + "new\n"))

    def test_non_utf8_user_file_backed_up(self):
        self.home.mkdir(parents=True)
        self.target.write_bytes(b"regras \xe7\xe3o\n")
        backup = write_generated(self.target, MARKER + "new\n")
        self.assertEqual(backup.read_bytes(), b"regras \xe7\xe3o\n")


class Run(unittest.TestCase):
    def test_end_to_end(self):
        root = tree(self)
        core = root / "core-repo"
        write(core / "core" / "AGENTS.core.md", "core rules\n")
        ov = Overlay(root / "overlay", "v0.1.0", True)
        (root / "overlay").mkdir()
        home = root / "codex home"
        lines = run(core, ov, home)
        self.assertIn("core rules", (home / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertTrue(any("AGENTS.md" in line for line in lines))
