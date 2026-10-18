# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import re
import unittest
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


class WorkflowTriggers(unittest.TestCase):
    def test_pull_request_runs_only_for_develop(self):
        for path in sorted(WORKFLOWS.glob("*.yml")):
            head = path.read_text(encoding="utf-8").split("\njobs:")[0]
            if re.search(r"^  pull_request:", head, re.MULTILINE) or re.search(
                r"^on:.*pull_request", head, re.MULTILINE
            ):
                self.assertRegex(
                    head, r"pull_request:\n    branches: \[develop\]", path.name
                )

    def test_promote_merges_a_clean_release_pull_request_directly(self):
        promote = (WORKFLOWS / "promote.yml").read_text(encoding="utf-8")
        self.assertIn(
            'gh pr merge "$n" --auto --merge --match-head-commit "$HEAD_SHA" '
            '|| gh pr merge "$n" --merge --match-head-commit "$HEAD_SHA"',
            promote,
        )


if __name__ == "__main__":
    unittest.main()
