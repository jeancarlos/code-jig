import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from harness import probe
from harness.install import stamp
from harness.tiers import Tier
from tests.util import tree, write

FAKE = r'''
import os, sys
args = sys.argv[1:]
home = os.environ["CODEX_HOME"]
if "prompt-input" in args:
    profile = args[args.index("--profile") + 1]
    if profile == "broken":
        sys.stderr.write("WARNING: proceeding\nError: broken.config.toml:1:9: bad\n"); sys.exit(1)
    agents = os.path.join(home, "AGENTS.md")
    text = open(agents, encoding="utf-8").read() if os.path.exists(agents) and profile != "hidden" else ""
    print('[{"type":"message","content":[{"text":%r}]}]' % (text + " <skills_instructions> - grilling: x"))
elif args and args[0] == "execpolicy":
    files = [args[i + 1] for i, a in enumerate(args) if a == "--rules"]
    for f in files:
        if "BROKEN" in open(f, encoding="utf-8").read():
            sys.stderr.write("Error: failed to parse policy at %s\n" % f); sys.exit(1)
    print('{"matchedRules":[]}')
elif args and args[0] == "exec":
    profile = args[args.index("--profile") + 1]
    sys.stderr.write("OpenAI Codex v0\n--------\nworkdir: x\nmodel: %s\nreasoning effort: %s\nsession id: 1\n--------\n"
                     % ("m-a" if profile != "wrong" else "zzz", "medium"))
    print("OK")
'''


class Probe(unittest.TestCase):
    def setUp(self):
        root = tree(self)
        self.home = root / "codex home"
        write(self.home / "AGENTS.md", stamp("core\n"))
        script = write(root / "fake_codex.py", FAKE)
        patcher = mock.patch.object(probe, "command", lambda b: [sys.executable, str(script)])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cwd = root
        self.bin = self.home / "codex"

    def test_prompt_ok(self):
        [(level, _, detail)] = probe.check_prompt(self.bin, self.home, self.cwd, [Tier("default", "m-a", "medium")])
        self.assertEqual(level, "ok")
        self.assertIn("AGENTS.md reaches the prompt", detail)

    def test_prompt_broken_profile_fails_with_error(self):
        [(level, _, detail)] = probe.check_prompt(self.bin, self.home, self.cwd, [Tier("broken", "m", "low")])
        self.assertEqual(level, "FAIL")
        self.assertIn("broken.config.toml", detail)

    def test_prompt_marker_missing_fails(self):
        [(level, _, detail)] = probe.check_prompt(self.bin, self.home, self.cwd, [Tier("hidden", "m", "low")])
        self.assertEqual(level, "FAIL")
        self.assertIn("AGENTS.md", detail)

    def test_no_binary_warns(self):
        [(level, _, _)] = probe.check_prompt(None, self.home, self.cwd, [Tier("default", "m", "low")])
        self.assertEqual(level, "warn")

    def test_timeout_is_a_fail_not_a_crash(self):
        with mock.patch.object(probe.subprocess, "run", side_effect=subprocess.TimeoutExpired("codex", 1)):
            [(level, _, detail)] = probe.check_prompt(self.bin, self.home, self.cwd, [Tier("default", "m", "low")])
        self.assertEqual(level, "FAIL")
        self.assertIn("timed out", detail)

    def test_live_matches_and_mismatches(self):
        checks = probe.check_live(self.bin, self.home, self.cwd,
                                  [Tier("default", "m-a", "medium"), Tier("wrong", "m-a", "medium")])
        self.assertEqual([c[0] for c in checks], ["ok", "FAIL"])

    def test_parse_summary_strips_ansi(self):
        s = "\x1b[1mmodel:\x1b[0m gpt-x\n\x1b[1mreasoning effort:\x1b[0m high\nuser\nmodel: later\n"
        self.assertEqual(probe.parse_summary(s), {"model": "gpt-x", "reasoning effort": "high"})

    def test_rules_load(self):
        write(self.home / "rules" / "default.rules", "ok\n")
        write(self.home / "rules" / "codex-harness-a.rules", "ok\n")
        [(level, _, detail)] = probe.check_rules(self.bin, self.home, self.cwd)
        self.assertEqual(level, "ok")
        self.assertIn("2", detail)

    def test_broken_rules_file_fails_naming_it(self):
        write(self.home / "rules" / "default.rules", "ok\n")
        write(self.home / "rules" / "codex-harness-bad.rules", "BROKEN\n")
        [(level, _, detail)] = probe.check_rules(self.bin, self.home, self.cwd)
        self.assertEqual(level, "FAIL")
        self.assertIn("codex-harness-bad.rules", detail)

    def test_no_rules_dir_is_ok(self):
        [(level, _, _)] = probe.check_rules(self.bin, self.home, self.cwd)
        self.assertEqual(level, "ok")

    def test_prompt_lists_installed_skills(self):
        [(level, _, _)] = probe.check_prompt(self.bin, self.home, self.cwd, [Tier("default", "m-a", "medium")], skills=["grilling"])
        self.assertEqual(level, "ok")
        [(level, _, detail)] = probe.check_prompt(self.bin, self.home, self.cwd, [Tier("default", "m-a", "medium")], skills=["nope"])
        self.assertEqual(level, "FAIL")
        self.assertIn("nope", detail)

    def test_skill_name_in_prose_is_not_a_loaded_skill(self):
        [(level, _, _)] = probe.check_prompt(self.bin, self.home, self.cwd, [Tier("default", "m-a", "medium")], skills=["skills_instructions"])
        self.assertEqual(level, "FAIL")


def prompt_with_skills(entries: list[tuple[str, int]]) -> str:
    lines = "\n".join(f"- {name}: {'d' * size} (file: r1/{name}/SKILL.md)" for name, size in entries)
    text = f"<skills_instructions>\n## Skills\n### Skill roots\n- `r1` = `/x`\n{lines}\n</skills_instructions>"
    return json.dumps([{"type": "message", "content": [{"type": "input_text", "text": text}]}])


class SkillsBudget(unittest.TestCase):
    def test_small_catalog_is_ok(self):
        level, _, detail = probe.skills_budget(prompt_with_skills([("a", 10), ("b", 20)]))
        self.assertEqual(level, "ok")
        self.assertIn("2 skills", detail)

    def test_large_catalog_warns_naming_the_largest(self):
        entries = [(f"s{i}", 300) for i in range(30)] + [("plugin:huge", 900)]
        level, _, detail = probe.skills_budget(prompt_with_skills(entries))
        self.assertEqual(level, "warn")
        self.assertIn("31 skills", detail)
        self.assertTrue(detail.split("largest: ")[1].startswith("plugin:huge"))
        self.assertIn("[[skills.config]]", detail)

    def test_no_catalog_gives_nothing(self):
        self.assertIsNone(probe.skills_budget("[]"))
        self.assertIsNone(probe.skills_budget("not json <skills_instructions> - a: b"))

    def test_check_prompt_adds_one_budget_line(self):
        with mock.patch.object(probe, "run_codex", return_value=subprocess.CompletedProcess([], 0, prompt_with_skills([("a", 5)]), "")):
            checks = probe.check_prompt(Path("codex"), tree(self), tree(self), [Tier("default", "m", "low"), Tier("deep", "m", "high")])
        self.assertEqual([c[1] for c in checks], ["tier default prompt", "tier deep prompt", "skills catalog"])
