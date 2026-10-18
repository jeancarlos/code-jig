# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "release_notes", ROOT / ".github" / "scripts" / "release_notes.py"
)
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

TEXT = "# Changelog\n\n## Unreleased\n\n- next\n\n## 1.2.0 - 2026-01-01\n\n- shipped\n"


class ReleaseNotes(unittest.TestCase):
    def test_tag_gets_its_section_and_the_upgrade_impact(self):
        out = release_notes.notes("v1.2.0", TEXT)
        self.assertIn("- shipped", out)
        self.assertNotIn("- next", out)
        self.assertIn(release_notes.UPGRADE, out)

    def test_tag_without_a_section_fails(self):
        with self.assertRaises(SystemExit):
            release_notes.notes("v1.3.0", TEXT)

    def test_release_candidate_uses_unreleased(self):
        self.assertIn("- next", release_notes.notes("v1.3.0-rc1", TEXT))

    def test_every_released_version_has_a_section(self):
        found = release_notes.sections(
            (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        )
        self.assertIn("Unreleased", found)
        self.assertIn("0.12.0", found)


if __name__ == "__main__":
    unittest.main()
