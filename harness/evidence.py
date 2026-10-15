import re
import statistics
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

from harness import analyze, paths

TEST_MARKERS = ("pytest", "unittest", "dotnet test", "npm test", "pnpm test", "yarn test", "run test", "vitest", "jest")
GRACE = timedelta(hours=2)
REWORK_DAYS = 14
MIN_COMMITS = 20
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
SESSIONS = """
SELECT t.id, t.cwd, t.started, MAX(x.ts) FROM threads t
LEFT JOIN (
  SELECT thread_id AS owner, ts FROM usage
  UNION ALL SELECT thread_id, ts FROM calls
  UNION ALL SELECT c.parent_id, u.ts FROM usage u JOIN threads c ON c.id = u.thread_id WHERE c.kind != 'main'
) x ON x.owner = t.id
WHERE t.kind = 'main' AND t.started >= ?
GROUP BY t.id
"""
LOG_FORMAT = "--format=%x01%H%x00%cI%x00%s%x00%b%x00"


@dataclass(frozen=True)
class Commit:
    sha: str
    when: datetime
    subject: str
    body: str
    hunks: dict[str, list[tuple[int, int, int, int]]] = field(default_factory=dict)


def is_test(cmd: str) -> bool:
    return any(m in cmd for m in TEST_MARKERS)


def _file(line: str, old: str | None) -> tuple[str | None, str | None]:
    name = line[6:].rstrip("\t") if line[4:6] in ("a/", "b/") else None
    return (name, None) if line.startswith("---") else (old, name or old)


def _add_hunk(hunks: dict, path: str | None, line: str) -> None:
    m = HUNK.match(line)
    if m and path:
        a, b, n, d = m.groups()
        hunks.setdefault(path, []).append((int(a), int(b or 1), int(n), int(d or 1)))


def _hunks(diff: str) -> dict[str, list[tuple[int, int, int, int]]]:
    hunks: dict[str, list[tuple[int, int, int, int]]] = {}
    old = path = None
    header = False
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            old = path = None
            header = True
        elif header and line.startswith(("--- ", "+++ ")):
            old, path = _file(line, old)
        elif line.startswith("@@"):
            header = False
            _add_hunk(hunks, path, line)
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


@dataclass(frozen=True)
class Session:
    id: str
    cwd: str | None
    start: datetime
    end: datetime


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sessions(con, since: str) -> list[Session]:
    out = []
    for tid, cwd, started, last in con.execute(SESSIONS, (since,)):
        start = _ts(started)
        out.append(Session(tid, cwd, start, max(start, _ts(last)) if last else start))
    return out


def _git(*args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-c", "core.quotepath=false", *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    except OSError:
        return None


def repo_root(cwd: str | None) -> Path | None:
    if not cwd or not Path(cwd).is_dir():
        return None
    r = _git("-C", cwd, "rev-parse", "--show-toplevel")
    return Path(r.stdout.strip()).resolve() if r and r.returncode == 0 and r.stdout.strip() else None


def git_log(root: Path, since: datetime) -> list[Commit]:
    r = _git("-C", str(root), "log", "--no-merges", f"--since={_iso(since)}", LOG_FORMAT, "-p", "--unified=0",
             "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames")
    return parse_log(r.stdout) if r and r.returncode == 0 else []


def by_repo(sess: list[Session]) -> tuple[dict[Path, list[Session]], list[str]]:
    repos: dict[Path, list[Session]] = {}
    unreachable: list[str] = []
    roots: dict[str | None, Path | None] = {}
    for s in sess:
        if s.cwd not in roots:
            roots[s.cwd] = repo_root(s.cwd)
        root = roots[s.cwd]
        if root is None:
            unreachable.append(s.cwd or "(no cwd)")
        else:
            repos.setdefault(root, []).append(s)
    return repos, sorted(set(unreachable))


def _owners(con, since: str | None = None):
    query = "SELECT c.thread_id, t.kind, t.parent_id, c.cmd, c.exit_code, c.escalated, c.skill, c.ts FROM calls c LEFT JOIN threads t ON t.id = c.thread_id"
    for tid, kind, parent, cmd, code, esc, skill, ts in con.execute(query):
        if since is None or (ts or "") >= since:
            yield (parent if kind != "main" and parent else tid), cmd or "", code, esc, skill


def discipline(con, owners: set[str]) -> dict:
    with_tests, runs, passed = set(), 0, 0
    for owner, cmd, code, _, _ in _owners(con):
        if owner in owners and is_test(cmd):
            with_tests.add(owner)
            if code is not None:
                runs += 1
                passed += code == 0
    return {"sessions": len(owners), "with_tests": len(with_tests), "test_runs": runs, "passed": passed}


def installed_skills() -> list[str]:
    root = paths.agents_skills()
    return sorted(p.parent.name for p in root.glob("*/SKILL.md")) if root.is_dir() else []


def use(con, since: str, installed: list[str]) -> dict:
    fired: dict[str, set[str]] = defaultdict(set)
    calls = escalated = 0
    for owner, _, _, esc, skill in _owners(con, since):
        calls += 1
        escalated += esc
        if skill:
            fired[skill].add(owner)
    skills = {k: len(v) for k, v in sorted(fired.items())}
    guardian = dict(con.execute("SELECT outcome, COUNT(*) FROM guardian WHERE ts >= ? GROUP BY outcome ORDER BY outcome", (since,)))
    return {"skills": skills, "never": sorted(set(installed) - set(skills)), "guardian": guardian,
            "calls": calls, "escalated": escalated}


def _tokens(con, since: str, ids: set[str]) -> tuple[dict[str, int], int, int]:
    tokens: dict[str, int] = defaultdict(int)
    inp = cached = 0
    for tid, kind, parent, i, c, o in con.execute("SELECT thread_id, kind, parent_id, input, cached, output FROM turn_usage WHERE ts >= ?", (since,)):
        owner = parent if kind != "main" and parent else tid
        if owner in ids:
            tokens[owner] += i + o
            inp += i
            cached += c
    return tokens, inp, cached


def cost(con, since: str, sess: list[Session], in_repos: list[Session], harness_commits: int) -> dict:
    ids, repo_ids = {s.id for s in sess}, {s.id for s in in_repos}
    tokens, inp, cached = _tokens(con, since, ids)
    total = sum(tokens.values())
    repo_total = sum(v for k, v in tokens.items() if k in repo_ids)
    minutes = [(s.end - s.start).total_seconds() / 60 for s in sess]
    return {"sessions": len(ids), "tokens": total, "tokens_per_session": total / len(ids) if ids else 0,
            "tokens_per_harness_commit": repo_total / harness_commits if harness_commits else None,
            "cache_hit": cached / inp if inp else 0.0,
            "compactions": con.execute("SELECT COUNT(*) FROM compactions WHERE ts >= ?", (since,)).fetchone()[0],
            "median_minutes": statistics.median(minutes) if minutes else 0}


def sample(commits: list[Commit], n: int) -> list[Commit]:
    if n <= 0 or not commits:
        return []
    if n >= len(commits):
        return list(commits)
    step = len(commits) / n
    return [commits[int(i * step)] for i in range(n)]


def changed_lines(c: Commit) -> int:
    return sum(d for hunks in c.hunks.values() for _, _, _, d in hunks)


def analyze_commit(root: Path, c: Commit, timeout: int = 600, path: str | None = None) -> list:
    tools = [t for t in analyze.TOOLS if t.name != "gitleaks-history"]
    with tempfile.TemporaryDirectory() as tmp:
        hooks = Path(tmp) / "hooks"
        hooks.mkdir()
        wt = Path(tmp) / "wt"
        g = ("-c", f"core.hooksPath={hooks}", "-C", str(root))
        made = _git(*g, "worktree", "add", "--detach", "--quiet", str(wt), c.sha)
        if not made or made.returncode != 0:
            return []
        try:
            found = analyze.run_tools(tools, wt, analyze.detect(wt), path=path, timeout=timeout).findings
            return [f for f in found if f.path in c.hunks]
        finally:
            _git(*g, "worktree", "remove", "--force", str(wt))


def _quality(cats: Counter, lines: int, sampled: int) -> dict:
    return {"sampled": sampled, "changed_lines": lines, "findings": dict(cats),
            "per_100_lines": {k: v * 100 / lines for k, v in cats.items()} if lines else {}}


def quality(root: Path, group: list[Commit], n: int, runner) -> dict | None:
    if n <= 0:
        return None
    picked = sample(group, n)
    cats: Counter = Counter()
    for c in picked:
        cats.update(f.category for f in runner(root, c))
    return _quality(cats, sum(changed_lines(c) for c in picked), len(picked))


def _total_quality(items: list[dict | None]) -> dict | None:
    items = [q for q in items if q]
    if not items:
        return None
    cats: Counter = Counter()
    for q in items:
        cats.update(q["findings"])
    return _quality(cats, sum(q["changed_lines"] for q in items), sum(q["sampled"] for q in items))


def repo_report(root: Path, sess: list[Session], since: datetime, now: datetime, analyze_n: int = 0, runner=None) -> dict:
    every = git_log(root, since)
    windows = [(s.start, s.end) for s in sess]
    groups = {"harness": [c for c in every if in_window(c.when, windows)],
              "baseline": [c for c in every if not in_window(c.when, windows)]}
    runner = runner or analyze_commit
    out = {"root": str(root), "sessions": len(sess)}
    for name, group in groups.items():
        out[name] = group_stats(group, every, now) | {"quality": quality(root, group, analyze_n, runner)}
    return out


def _total(groups: list[dict]) -> dict:
    return rate(sum(g["commits"] for g in groups), sum(g["mature"] for g in groups), sum(g["reworked"] for g in groups))


def report(con, since: datetime, now: datetime, repo: Path | None = None, analyze_n: int = 0, runner=None, timeout: int = 600) -> dict:
    iso = _iso(since)
    sess = sessions(con, iso)
    repos, unreachable = by_repo(sess)
    if repo is not None:
        root = repo_root(str(repo))
        repos = {root: repos.get(root, [])} if root else {}
    runner = runner or partial(analyze_commit, timeout=timeout)
    per = [repo_report(root, s, since, now, analyze_n, runner) for root, s in sorted(repos.items())]
    totals = {g: _total([r[g] for r in per]) | {"quality": _total_quality([r[g]["quality"] for r in per])} for g in ("harness", "baseline")}
    in_repos = [s for group in repos.values() for s in group]
    return {"since": iso, "days": (now - since).days, "repos": per, "totals": totals, "unreachable": unreachable,
            "discipline": discipline(con, {s.id for s in in_repos}),
            "use": use(con, iso, installed_skills()),
            "cost": cost(con, iso, sess, in_repos, totals["harness"]["commits"])}
