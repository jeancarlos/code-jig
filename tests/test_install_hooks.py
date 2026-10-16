import json
import os
import stat
import unittest

from codejig import paths
from codejig.install import CLAUDE_CODE_WATERMARK_STATUS, HOOK_STATUS, hook_commands, merged_claude_code_hooks, merged_hooks, run, write_merged
from codejig.overlay import Overlay
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

    def test_malformed_nested_hooks_names_file(self):
        for hooks in (1, True, "command", {}, None, [1]):
            with self.subTest(hooks=hooks):
                original = json.dumps({"hooks": {"Stop": [{"hooks": hooks}]}})
                write(self.path, original)
                with self.assertRaisesRegex(ValueError, "hooks.json"):
                    merged_hooks(self.path, "p", "w")
                self.assertEqual(self.path.read_text(encoding="utf-8"), original)

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


class HookIsolation(unittest.TestCase):
    def test_hook_ignores_modules_planted_in_the_session_cwd(self):
        import subprocess
        import sys
        from codejig import paths
        root = tree(self)
        cwd = root / "repo"
        marker = root / "pwned"
        planted = f"open({str(marker)!r}, 'w').close()\n"
        write(cwd / "codejig" / "__init__.py", planted)
        write(cwd / "json.py", planted)
        posix, _ = hook_commands(paths.CORE, root / "codex home", sys.executable)
        args = posix.split(" -m codejig ", 1)[0].split()
        exe = [a.strip("'") for a in args if not a.startswith("PYTHONPATH=")]
        env = {"PYTHONPATH": str(paths.CORE), "PATH": "/usr/bin:/bin", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
               "XDG_DATA_HOME": str(root / "state data"), "LOCALAPPDATA": str(root / "state data")}
        r = subprocess.run([*exe, "-m", "codejig", "--codex-home", str(root / "codex home"), "collect"],
                           cwd=cwd, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.stdout, "{}\n")
        self.assertFalse(marker.exists())


class HookRunsInstalledCopy(unittest.TestCase):
    def test_hook_points_at_a_copy_outside_the_core(self):
        root = tree(self)
        core = root / "core-repo"
        write(core / "core" / "AGENTS.core.md", "core\n")
        write(core / "core" / "tiers.toml", 'default = "medium"\n')
        write(core / "codejig" / "__init__.py", 'VERSION = "x"\n')
        write(core / "codejig" / "collect.py", "A = 1\n")
        ov = root / "overlay"
        write(ov / "profiles.toml", 'default = "m"\n')
        home = root / "codex home"
        run(core, Overlay(ov, "v0.3.0", True), home)
        lib = paths.state_dir() / "lib"
        self.assertIn("A = 1", (lib / "codejig" / "collect.py").read_text(encoding="utf-8"))
        command = json.loads((home / "hooks.json").read_text(encoding="utf-8"))["hooks"]["Stop"][-1]["hooks"][0]["command"]
        self.assertIn(str(lib), command)
        self.assertNotIn(str(core), command)


class HookInterpreter(unittest.TestCase):
    def test_flags_and_base_interpreter(self):
        import sys
        from unittest import mock
        from codejig import install
        posix, windows = hook_commands(tree(self), tree(self), "/usr/bin/python3")
        self.assertIn(" -P -s -m codejig ", posix)
        self.assertIn(" -P -s -m codejig ", windows)
        with mock.patch.object(sys, "_base_executable", "/opt/base/python3", create=True):
            self.assertEqual(install.interpreter(), "/opt/base/python3")


class CodexWatermarkHook(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.path = self.root / "hooks.json"

    def test_codex_gets_one_posttooluse_watermark_hook_next_to_collect(self):
        write(self.path, json.dumps({"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": "mine"}]}]}}))
        once = merged_hooks(self.path, "p", "w", watermark=("wp", "ww"))
        write(self.path, once)
        data = json.loads(merged_hooks(self.path, "p", "w", watermark=("wp2", "ww2")))
        commands = [h["command"] for g in data["hooks"]["PostToolUse"] for h in g["hooks"]]
        self.assertEqual(commands, ["mine", "wp2"])
        self.assertEqual(len(data["hooks"]["Stop"]), 1)

    def test_settings_keep_their_permissions(self):
        settings = self.root / "settings.json"
        write(settings, "{}\n")
        os.chmod(settings, 0o600)
        write_merged(settings, '{"hooks": {}}\n')
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(settings).st_mode), 0o600)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.endswith(".tmp")), [])


class ClaudeCodeHooks(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.path = self.root / ".claude" / "settings.json"

    def test_absent_file_gets_posttooluse_hooks(self):
        data = json.loads(merged_claude_code_hooks(self.path, "cmd"))
        self.assertIn("PostToolUse", data["hooks"])
        [group] = data["hooks"]["PostToolUse"]
        self.assertEqual(group["matcher"], "Write|Edit|MultiEdit|NotebookEdit")
        self.assertEqual(group["hooks"][0]["timeout"], 10)

    def test_user_hooks_survive_and_ours_are_replaced(self):
        user = {"hooks": {"PostToolUse": [
            {"matcher": "OtherTool", "hooks": [{"type": "command", "command": "x"}]},
            {"hooks": [{"type": "command", "command": "notify"}]}
        ]}}
        write(self.path, json.dumps(user))
        once = merged_claude_code_hooks(self.path, "cmd1")
        write(self.path, once)
        data = json.loads(merged_claude_code_hooks(self.path, "cmd2"))
        watermarks = [g for g in data["hooks"]["PostToolUse"] if any(
            h.get("statusMessage") == CLAUDE_CODE_WATERMARK_STATUS for h in g.get("hooks") or [])]
        self.assertEqual(len(watermarks), 1)
        self.assertEqual(watermarks[0]["hooks"][0]["command"], "cmd2")
        other = [g for g in data["hooks"]["PostToolUse"] if g.get("matcher") == "OtherTool"]
        self.assertEqual(len(other), 1)
        notify = [g for g in data["hooks"]["PostToolUse"] if not g.get("matcher") and not any(
            h.get("statusMessage") for h in g.get("hooks") or [])]
        self.assertEqual(len(notify), 1)

    def test_watermark_hooks_have_correct_status(self):
        data = json.loads(merged_claude_code_hooks(self.path, "cmd"))
        for group in data["hooks"]["PostToolUse"]:
            if group.get("statusMessage") == CLAUDE_CODE_WATERMARK_STATUS:
                self.assertEqual(group["hooks"][0]["type"], "command")
                self.assertIn("cmd", group["hooks"][0]["command"])

    def test_malformed_nested_hooks_names_file(self):
        for hooks in (1, True, "command", {}, None, [1]):
            with self.subTest(hooks=hooks):
                original = json.dumps({"hooks": {"PostToolUse": [{"hooks": hooks}]}})
                write(self.path, original)
                with self.assertRaisesRegex(ValueError, "settings.json"):
                    merged_claude_code_hooks(self.path, "cmd")
                self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_write_merged_settings_backs_up_only_on_change(self):
        write(self.path, '{"hooks": {}}\n')
        self.assertIsNotNone(write_merged(self.path, '{"hooks": {"PostToolUse": []}}\n'))
        self.assertIsNone(write_merged(self.path, '{"hooks": {"PostToolUse": []}}\n'))
        self.assertEqual(len(list(self.path.parent.glob("settings.json.bak-*"))), 1)
