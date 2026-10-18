# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import re
import sys
from pathlib import Path

UPGRADE = (
    "Upgrade: `pipx upgrade code-jig`, set `core_version` in your overlay to this version, "
    "then run `code-jig install` and `code-jig doctor`. "
    "See docs/runbooks/upgrade-and-rollback.md."
)


def sections(text):
    parts = re.split(r"^## (\S+).*\n", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def notes(tag, text):
    found = sections(text)
    version = tag.removeprefix("v")
    body = found.get(version)
    if body is None and "-rc" in version:
        body = found.get(version.split("-rc")[0]) or found.get("Unreleased")
    if not body:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    return f"{body}\n\n{UPGRADE}\n"


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    sys.stdout.write(
        notes(sys.argv[1], (root / "CHANGELOG.md").read_text(encoding="utf-8"))
    )
