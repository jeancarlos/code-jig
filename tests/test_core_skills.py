import json
import re
import unittest

from codejig import paths

SKILLS = paths.CORE / "skills"
EXPECTED = {"bug-hunt", "code-analysis", "codegen", "cross-review", "grilling", "hld-trace", "improve", "redacao", "regression-tests", "skill-validate", "web-consensus"}
OPT_OUTS = {
    r"\bsemgrep\b": ("--metrics=off",),
    r"\bkiota\b": ("KIOTA_CLI_TELEMETRY_OPTOUT=1",),
    r"\bdotnet\b": ("DOTNET_CLI_TELEMETRY_OPTOUT=1",),
    r"\bosv-scanner\b": ("--offline",),
    r"\btrivy\b": ("--disable-telemetry", "--skip-version-check"),
}


def frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return {}
    end = lines.index("---", 1)
    meta = dict(line.split(": ", 1) for line in lines[1:end] if ": " in line)
    return {k: json.loads(v) if v.startswith('"') else v for k, v in meta.items()}


class CoreSkills(unittest.TestCase):
    def test_expected_skills_ship(self):
        self.assertEqual({p.parent.name for p in SKILLS.glob("*/SKILL.md")}, EXPECTED)

    def test_frontmatter(self):
        for path in SKILLS.glob("*/SKILL.md"):
            with self.subTest(skill=path.parent.name):
                meta = frontmatter(path.read_text(encoding="utf-8"))
                self.assertEqual(meta.get("name"), path.parent.name)
                self.assertTrue(re.fullmatch(r"[a-z0-9-]{1,64}", meta["name"]))
                self.assertTrue(meta.get("description", "").startswith("Use when"))
                self.assertLessEqual(len(meta["description"]), 1024)

    def test_telemetry_opt_outs(self):
        for path in SKILLS.glob("*/SKILL.md"):
            text = path.read_text(encoding="utf-8")
            for tool, flags in OPT_OUTS.items():
                if re.search(tool, text, re.IGNORECASE):
                    for flag in flags:
                        with self.subTest(skill=path.parent.name, tool=tool, flag=flag):
                            self.assertIn(flag, text)

    def test_frontmatter_parser(self):
        self.assertEqual(frontmatter("---\nname: a\ndescription: Use when x: y\n---\nbody"), {"name": "a", "description": "Use when x: y"})
        self.assertEqual(frontmatter("no header"), {})
        self.assertEqual(frontmatter("---\nname: a\n"), {})
