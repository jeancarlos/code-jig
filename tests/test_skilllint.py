import contextlib
import io
import types
import unittest

from harness import paths, skilllint
from tests.util import tree, write

GOOD = "---\nname: demo\ndescription: Use when the user asks for a demo.\n---\n\n# Demo\n\nDo it.\n\n## Common mistakes\n\nNone.\n"


def levels(path) -> dict[str, str]:
    return {msg: level for level, msg in skilllint.check(path)}


class Check(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)

    def skill(self, text: str, name: str = "demo"):
        return write(self.root / name / "SKILL.md", text)

    def test_good_skill_is_clean(self):
        self.assertEqual(skilllint.check(self.skill(GOOD)), [])

    def test_missing_or_unclosed_frontmatter_fails(self):
        for text in ("# no header\n", "---\nname: demo\n", "---\n---\nbody\n"):
            with self.subTest(text=text):
                [(level, msg)] = skilllint.check(self.skill(text))
                self.assertEqual(level, "FAIL")
                self.assertIn("frontmatter", msg)

    def test_name_rules(self):
        bad = self.skill(GOOD.replace("name: demo", "name: has space"))
        self.assertIn("FAIL", levels(bad).values())
        long = self.skill(GOOD.replace("name: demo", "name: " + "a" * 65), "a" * 65)
        self.assertIn("FAIL", levels(long).values())
        other = self.skill(GOOD.replace("name: demo", "name: other"))
        self.assertEqual(list(levels(other).values()), ["WARN"])

    def test_description_rules(self):
        cases = {
            "description: Does demos.": "FAIL",
            'description: Use when I want a demo.': "FAIL",
            'description: Use when the user says "I want a demo".': None,
            "description: Use when you want a demo.": "WARN",
            "description: Use when " + "x" * 600: "WARN",
        }
        for line, want in cases.items():
            with self.subTest(line=line):
                got = set(levels(self.skill(GOOD.replace("description: Use when the user asks for a demo.", line))).values())
                self.assertEqual(got, {want} if want else set())

    def test_missing_description_fails(self):
        self.assertIn("FAIL", levels(self.skill(GOOD.replace("description: Use when the user asks for a demo.\n", ""))).values())

    def test_folded_description_is_read(self):
        text = GOOD.replace("description: Use when the user asks for a demo.", "description: >\n  Use when the user\n  asks for a demo.")
        self.assertEqual(skilllint.check(self.skill(text)), [])

    def test_body_warnings(self):
        body = GOOD.replace("Do it.", "Do it on 2026-01-02. " + "word " * 600 + "\n```\n" + "x\n" * 60 + "```\n")
        msgs = " ".join(levels(self.skill(body)))
        for needle in ("2026-01-02", "words", "60-line"):
            self.assertIn(needle, msgs)
        self.assertIn("Common mistakes", " ".join(levels(self.skill(GOOD.replace("## Common mistakes", "## Notes")))))

    def test_force_loading_link_fails(self):
        self.assertIn("FAIL", levels(self.skill(GOOD.replace("Do it.", "See @skills/other/SKILL.md."))).values())

    def test_cli_exit_codes_and_directories(self):
        self.skill(GOOD)
        bad = self.skill("# nothing\n", "broken")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(skilllint.cli(types.SimpleNamespace(path=[str(self.root / "demo")])), 0)
            self.assertEqual(skilllint.cli(types.SimpleNamespace(path=[str(bad.parent), str(self.root / "missing")])), 1)
        self.assertIn("not found", out.getvalue())


class CoreSkillsLint(unittest.TestCase):
    def test_no_core_skill_fails(self):
        for path in sorted((paths.CORE / "skills").glob("*/SKILL.md")):
            with self.subTest(skill=path.parent.name):
                self.assertEqual([m for lv, m in skilllint.check(path) if lv == "FAIL"], [])


if __name__ == "__main__":
    unittest.main()
