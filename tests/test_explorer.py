import tomllib
import unittest

from harness.doctor import check_roles
from harness.install import is_generated, run
from harness.overlay import Overlay
from tests.util import tree, write


def setup(test, tiers_toml='default = "medium"\nbulk = "low"\n', models='default = "m-a"\nbulk = "cheap"\n'):
    root = tree(test)
    core = root / "core-repo"
    write(core / "core" / "AGENTS.core.md", "core\n")
    write(core / "core" / "tiers.toml", tiers_toml)
    write(core / "core" / "agents" / "explorer.toml",
          'name = "explorer"\ndescription = "Find things."\ndeveloper_instructions = "Read only."\n')
    ov = Overlay(root / "overlay", "v0.8.0", True)
    write(ov.root / "profiles.toml", models)
    return core, ov, root / "codex home"


class ExplorerRole(unittest.TestCase):
    def test_role_runs_on_the_bulk_tier(self):
        core, ov, home = setup(self)
        run(core, ov, home)
        path = home / "agents" / "explorer.toml"
        self.assertTrue(is_generated(path))
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data, {"model": "cheap", "model_reasoning_effort": "low", "name": "explorer",
                                "description": "Find things.", "developer_instructions": "Read only."})

    def test_user_role_file_is_backed_up(self):
        core, ov, home = setup(self)
        write(home / "agents" / "explorer.toml", 'name = "explorer"\n')
        run(core, ov, home)
        [backup] = (home / "agents").glob("explorer.toml.bak-*")
        self.assertEqual(backup.read_text(encoding="utf-8"), 'name = "explorer"\n')

    def test_no_bulk_tier_writes_no_role(self):
        core, ov, home = setup(self, 'default = "medium"\n', 'default = "m-a"\n')
        run(core, ov, home)
        self.assertFalse((home / "agents" / "explorer.toml").exists())

    def test_doctor_ok_then_stale(self):
        core, ov, home = setup(self)
        run(core, ov, home)
        [(level, _, detail)] = check_roles(home, core, ov)
        self.assertEqual((level, detail), ("ok", "explorers run cheap at low"))
        write(ov.root / "profiles.toml", 'default = "m-a"\nbulk = "other"\n')
        [(level, _, _)] = check_roles(home, core, ov)
        self.assertEqual(level, "warn")

    def test_doctor_missing(self):
        core, ov, home = setup(self)
        [(level, _, detail)] = check_roles(home, core, ov)
        self.assertEqual(level, "warn")
        self.assertIn("harness install", detail)


class ShippedRole(unittest.TestCase):
    def test_core_role_parses_and_keeps_its_contract(self):
        from harness import paths
        data = tomllib.loads((paths.CORE / "core" / "agents" / "explorer.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "explorer")
        self.assertNotIn("model", data)
        self.assertIn("line", data["developer_instructions"])
        self.assertTrue(data["description"].strip())


if __name__ == "__main__":
    unittest.main()
