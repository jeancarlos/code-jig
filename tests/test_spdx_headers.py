# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = ["# SPDX-FileCopyrightText: 2026 Jean Souza", "# SPDX-License-Identifier: Apache-2.0"]
SKIPPED = ("tests/fixtures/", "skills/")


def tracked_python() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.py"], capture_output=True, text=True, check=True).stdout
    return [f for f in out.split() if not f.startswith(SKIPPED)]


@unittest.skipUnless((ROOT / ".git").exists(), "needs a git checkout")
class SpdxHeaders(unittest.TestCase):
    def test_every_source_file_names_its_copyright_holder_and_license(self):
        bad = []
        for name in tracked_python():
            lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
            if lines[:1] and lines[0].startswith("#!"):
                lines = lines[1:]
            if lines[:2] != HEADER:
                bad.append(name)
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
