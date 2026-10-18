# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "same_major.py"
spec = importlib.util.spec_from_file_location("same_major", SCRIPT)
same_major = importlib.util.module_from_spec(spec)
spec.loader.exec_module(same_major)

CASES = (
    ("chore(deps): bump ruff from 0.17.0 to 0.17.1", True),
    ("chore(deps): bump ruff from 0.17.0 to 0.17.1 in /ci", True),
    ("chore(deps): bump actions/checkout from 7.0.1 to 7.1.0", True),
    ("chore(deps): bump coverage from 7.16.2 to 7.99 in /ci", True),
    ("chore(deps): bump @openai/codex from 1.2.3 to 1.4.0 in /ci/npm", True),
    ("chore(deps): bump agnix from v1.57.0 to v1.58.0", True),
    ("chore(deps): bump a from 2.0.0-rc.1 to 2.0.0", True),
    ("chore(deps): bump knip from 6.41.0 to 7.0.0", False),
    ("chore(deps): bump knip from 6.41.0 to 7.0.0 in /ci/npm", False),
    ("chore(deps): bump ruff from 0.17.0 to 0.18.0 in /ci", False),
    ("chore(deps): bump @openai/codex from 0.162.0 to 0.170.1 in /ci/npm", False),
    ("chore(deps): bump agnix from v0.57.0 to v0.58.0", False),
    ("chore(deps): bump a from 0.9.9 to 1.0.0", False),
    ("chore(deps): bump the actions group with 3 updates", False),
    ("chore(deps): bump the pip group in /ci with 2 updates", False),
    ("chore(deps): bump the npm group across 2 directories with 4 updates", False),
    ("chore(deps): update a requirement from ~=1.0 to ~=1.1 in /ci", False),
    ("chore(deps): bump a from 1abc to 1def", False),
    ("chore(deps): bump a from 1.0.0 to 1.0.1\nrm -rf", False),
    ("chore(deps): bump a from 1.0.0 to 1.0.1 in /ci\nrm -rf", False),
    ("chore(deps): bump a from 1.0.0 to 1.0.1 in ci", False),
    ("chore(deps): bump a from 1.0.0 to 1.0.1 in /ci and more", False),
    ("chore(deps): bump x from 1.0.0 to 1.0.1 and y from 2.0.0 to 2.0.1", False),
    ("chore(deps): bump actions/checkout from 3d3c42e to 5fda3b9", False),
    ("fix: bump a from 1.0.0 to 1.0.1", False),
    ("", False),
)


class SameMajor(unittest.TestCase):
    def test_titles(self):
        for title, expected in CASES:
            with self.subTest(title=title):
                self.assertIs(same_major.same_major(title), expected)


if __name__ == "__main__":
    unittest.main()
