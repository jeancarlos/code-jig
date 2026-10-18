# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "coverage_gate.py"
spec = importlib.util.spec_from_file_location("coverage_gate", SCRIPT)
coverage_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage_gate)


def report(lines: tuple[int, int], branches: tuple[int, int]) -> dict:
    return {"totals": {"covered_lines": lines[0], "num_statements": lines[1],
                       "covered_branches": branches[0], "num_branches": branches[1]}}


class CoverageGate(unittest.TestCase):
    def test_both_floors_met_passes(self):
        self.assertEqual(coverage_gate.gate(report((90, 100), (80, 100))), [])

    def test_statement_coverage_under_90_fails(self):
        self.assertEqual(coverage_gate.gate(report((89, 100), (90, 100))), ["statement coverage 89.0% is below 90%"])

    def test_branch_coverage_under_80_fails_even_when_statements_are_high(self):
        self.assertEqual(coverage_gate.gate(report((99, 100), (79, 100))), ["branch coverage 79.0% is below 80%"])

    def test_both_failing_reports_both(self):
        self.assertEqual(len(coverage_gate.gate(report((1, 100), (1, 100)))), 2)

    def test_no_branches_counts_as_covered(self):
        self.assertEqual(coverage_gate.gate(report((90, 100), (0, 0))), [])

    def test_main_reads_the_json_and_exits_by_the_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            for rep, code in ((report((95, 100), (90, 100)), 0), (report((50, 100), (90, 100)), 1)):
                path = Path(d) / "c.json"
                path.write_text(json.dumps(rep), encoding="utf-8")
                self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), str(path)], check=False, capture_output=True).returncode, code)


if __name__ == "__main__":
    unittest.main()
