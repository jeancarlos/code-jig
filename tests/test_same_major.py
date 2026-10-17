import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "same_major.py"
spec = importlib.util.spec_from_file_location("same_major", SCRIPT)
same_major = importlib.util.module_from_spec(spec)
spec.loader.exec_module(same_major)


class SameMajor(unittest.TestCase):
    def test_minor_and_patch_bumps_merge(self):
        for title in ("chore(deps): bump ruff from 0.17.0 to 0.17.1", "chore(deps): bump actions/checkout from 7.0.1 to 7.1.0",
                      "chore(deps): bump agnix from v0.57.0 to v0.58.0", "chore(deps): bump coverage from 7.16.2 to 7.99"):
            with self.subTest(title=title):
                self.assertTrue(same_major.same_major(title))

    def test_major_bumps_wait_for_a_human(self):
        self.assertFalse(same_major.same_major("chore(deps): bump knip from 6.41.0 to 7.0.0"))

    def test_anything_else_is_left_alone(self):
        for title in ("chore(deps): bump the actions group with 3 updates", "chore(deps): bump a from 1abc to 2def",
                      "chore(deps): bump a from 1.0.0 to 1.0.1\nrm -rf", "fix: bump a from 1.0.0 to 1.0.1", "",
                      "chore(deps): bump x from 1.0.0 to 1.0.1 and y from 2.0.0 to 2.0.1"):
            with self.subTest(title=title):
                self.assertFalse(same_major.same_major(title))


if __name__ == "__main__":
    unittest.main()
