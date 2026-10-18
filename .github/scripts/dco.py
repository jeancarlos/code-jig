# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import re
import subprocess
import sys

SIGNED = re.compile(r"^Signed-off-by:\s+\S.*<([^<>@\s]+@[^<>\s]+)>\s*$", re.MULTILINE | re.IGNORECASE)
SEPARATOR = "\x1f"


def is_bot(name, email):
    return name.endswith("[bot]") or email.endswith("[bot]@users.noreply.github.com")


def unsigned(commits):
    problems = []
    for sha, name, email, committer_email, message in commits:
        if is_bot(name, email):
            continue
        signers = {s.lower() for s in SIGNED.findall(message)}
        if not signers & {email.lower(), committer_email.lower()}:
            problems.append(f"{sha[:12]}: no \"Signed-off-by: {name} <{email}>\" line (commit with git commit -s)")
    return problems


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def read_range(base, head):
    fields = SEPARATOR.join(["%H", "%an", "%ae", "%ce", "%B"])
    return [
        tuple(git("log", "-1", f"--format={fields}", sha).rstrip("\n").split(SEPARATOR, 4))
        for sha in git("rev-list", "--no-merges", f"{base}..{head}").split()
    ]


if __name__ == "__main__":
    problems = unsigned(read_range(sys.argv[1], sys.argv[2]))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        sys.exit(1)
