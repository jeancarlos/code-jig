import json
import unittest

from harness.install import HOOK_STATUS, hook_commands, merged_hooks, run, write_merged
from harness.overlay import Overlay
from tests.util import tree, write

USER = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "notify-send done"}]}],
                  "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]}}


def ours(data):
    return [g for g in data["hooks"]["Stop"] if any(h.get("statusMessage") == HOOK_STATUS for h in g["hooks"])]


class Hooks(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.path = self.root / "codex home" / "hooks.json"

    def test_absent_file_gets_one_group(self):
        data = json.loads(merged_hooks(self.path, "p", "w"))
        [group] = ours(data)
        self.assertEqual(group["hooks"][0], {"type": "command", "command": "p", "commandWindows": "w", "timeout": 60, "statusMessage": HOOK_STATUS})

    def test_user_hooks_survive_and_ours_is_replaced(self):
        write(self.path, json.dumps(USER))
        once = merged_hooks(self.path, "p1", "w1")
        write(self.path, once)
        data = json.loads(merged_hooks(self.path, "p2", "w2"))
        self.assertEqual(len(ours(data)), 1)
        self.assertEqual(ours(data)[0]["hooks"][0]["command"], "p2")
        self.assertIn({"hooks": [{"type": "command", "command": "notify-send done"}]}, data["hooks"]["Stop"])
        self.assertEqual(data["hooks"]["PreToolUse"], USER["hooks"]["PreToolUse"])

    def test_malformed_names_file(self):
        write(self.path, "{not json")
        with self.assertRaisesRegex(ValueError, "hooks.json"):
            merged_hooks(self.path, "p", "w")
        write(self.path, '{"hooks": []}')
        with self.assertRaisesRegex(ValueError, "hooks.json"):
            merged_hooks(self.path, "p", "w")

    def test_write_merged_backs_up_only_on_change(self):
        write(self.path, '{"hooks": {}}\n')
        self.assertIsNotNone(write_merged(self.path, '{"hooks": {"Stop": []}}\n'))
        self.assertIsNone(write_merged(self.path, '{"hooks": {"Stop": []}}\n'))
        self.assertEqual(len(list(self.path.parent.glob("hooks.json.bak-*"))), 1)

    def test_commands_quote_spaces(self):
        posix, windows = hook_commands(self.root / "core dir", self.root / "codex home", "/usr/bin/python3")
        self.assertIn("'", posix)
        self.assertTrue(posix.endswith(" collect"))
        self.assertIn('set "PYTHONPATH=', windows)
        self.assertIn('--codex-home "', windows)

    def test_malformed_hooks_stops_install_before_writing(self):
        core = self.root / "core-repo"
        write(core / "core" / "AGENTS.core.md", "core\n")
        write(core / "core" / "tiers.toml", 'default = "medium"\n')
        ov = self.root / "overlay"
        write(ov / "profiles.toml", 'default = "m"\n')
        write(self.path, "{bad")
        with self.assertRaises(ValueError):
            run(core, Overlay(ov, "v0.3.0", True), self.path.parent)
        self.assertFalse((self.path.parent / "AGENTS.md").exists())
