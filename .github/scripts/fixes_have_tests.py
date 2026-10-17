import re
import subprocess
import sys

LOGGED = re.compile(r"(feat|fix)(\(.+\))?!?:")
EXEMPT = re.compile(r"^No-Test:\s*\S", re.MULTILINE)


def missing_tests(changes):
    return [
        f"{subject}: no change under tests/ (add a test, or a \"No-Test: <reason>\" line)"
        for subject, body, files in changes
        if LOGGED.match(subject) and not EXEMPT.search(body) and not any(f.startswith("tests/") for f in files)
    ]


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def read_range(base, head):
    shas = git("rev-list", "--no-merges", f"{base}..{head}").split()
    return [
        (
            git("log", "-1", "--format=%s", sha).strip(),
            git("log", "-1", "--format=%b", sha),
            git("show", "--name-only", "--format=", sha).split(),
        )
        for sha in shas
    ]


if __name__ == "__main__":
    problems = missing_tests(read_range(sys.argv[1], sys.argv[2]))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        sys.exit(1)
