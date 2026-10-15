import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

TEST_MARKERS = ("pytest", "unittest", "dotnet test", "npm test", "pnpm test", "yarn test", "run test", "vitest", "jest")
GRACE = timedelta(hours=2)
REWORK_DAYS = 14
MIN_COMMITS = 20
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class Commit:
    sha: str
    when: datetime
    subject: str
    body: str
    hunks: dict[str, list[tuple[int, int, int, int]]] = field(default_factory=dict)


def is_test(cmd: str) -> bool:
    return any(m in cmd for m in TEST_MARKERS)


def _hunks(diff: str) -> dict[str, list[tuple[int, int, int, int]]]:
    hunks: dict[str, list[tuple[int, int, int, int]]] = {}
    old = path = None
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            old = path = None
        elif line.startswith("--- "):
            old = line[6:].rstrip("\t") if line.startswith("--- a/") else None
        elif line.startswith("+++ "):
            path = line[6:].rstrip("\t") if line.startswith("+++ b/") else old
        elif line.startswith("@@") and path:
            m = HUNK.match(line)
            if m:
                a, b, n, d = m.groups()
                hunks.setdefault(path, []).append((int(a), int(b or 1), int(n), int(d or 1)))
    return hunks


def parse_log(text: str) -> list[Commit]:
    commits = []
    for chunk in text.split("\x01")[1:]:
        sha, when, subject, body, diff = chunk.split("\x00", 4)
        commits.append(Commit(sha, datetime.fromisoformat(when), subject, body, _hunks(diff)))
    return commits


def in_window(when: datetime, windows: list[tuple[datetime, datetime]]) -> bool:
    return any(start <= when <= end + GRACE for start, end in windows)


def _same_lines(target: Commit, later: Commit) -> bool:
    for path, hunks in later.hunks.items():
        mine = target.hunks.get(path, ())
        for a, b, _, _ in hunks:
            if b and any(d and a <= n + d - 1 and n <= a + b - 1 for _, _, n, d in mine):
                return True
    return False


def reworked(target: Commit, every: list[Commit], days: int = REWORK_DAYS) -> bool:
    end = target.when + timedelta(days=days)
    names = (f'Revert "{target.subject}"', f"fixup! {target.subject}", f"squash! {target.subject}")
    for later in every:
        if not target.when < later.when <= end:
            continue
        if later.subject in names or target.sha in later.body or _same_lines(target, later):
            return True
    return False


def rate(commits: int, mature: int, reworked: int) -> dict:
    return {"commits": commits, "mature": mature, "reworked": reworked,
            "rework_rate": reworked / mature if mature >= MIN_COMMITS else None}


def group_stats(group: list[Commit], every: list[Commit], now: datetime) -> dict:
    mature = [c for c in group if c.when <= now - timedelta(days=REWORK_DAYS)]
    return rate(len(group), len(mature), sum(reworked(c, every) for c in mature))
