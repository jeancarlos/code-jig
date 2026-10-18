# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import json
import sys

STATEMENTS = 90.0
BRANCHES = 80.0


def percent(covered: int, total: int) -> float:
    return 100.0 if total == 0 else 100.0 * covered / total


def gate(report: dict) -> list[str]:
    t = report["totals"]
    found = {
        "statement": (percent(t["covered_lines"], t["num_statements"]), STATEMENTS),
        "branch": (percent(t["covered_branches"], t["num_branches"]), BRANCHES),
    }
    return [f"{kind} coverage {got:.1f}% is below {floor:.0f}%" for kind, (got, floor) in found.items() if got < floor]


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        failures = gate(json.load(f))
    for line in failures:
        print(line, file=sys.stderr)
    sys.exit(1 if failures else 0)
