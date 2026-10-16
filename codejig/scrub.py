import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from codejig.watermark import clean_message, has_watermark

EXPORT = ["fast-export", "--no-data", "--show-original-ids", "--reencode=no", "--signed-tags=strip",
          "--tag-of-filtered-object=rewrite", "--reference-excluded-parents"]
ALL = ("--branches", "--tags")
SIGNATURE = (b"gpgsig ", b"gpgsig-sha256 ")
EMAIL = re.compile(rb"<([^>]*)>")


class Abort(Exception):
    pass


def _git(repo: Path, *args: str, stdin: bytes | None = None, check: bool = True) -> bytes:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, input=stdin, check=False)
    if check and r.returncode:
        raise Abort(f"git {' '.join(args)} failed: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def my_emails(repo: Path, extra: list[str] = ()) -> set[str]:
    """user.email, every codejig.email value, and `extra`, lower-cased."""
    found = []
    for key in ("user.email", "codejig.email"):
        r = subprocess.run(["git", "-C", str(repo), "config", "--get-all", key], capture_output=True, text=True, encoding="utf-8", check=False)
        found += r.stdout.split()
    return {e.lower() for e in [*found, *extra] if e}


def attributed(repo: Path, emails: set[str], revs: tuple[str, ...] = ALL) -> list[str]:
    out = _git(repo, "log", "--format=%H%x00%ae%x00%B%x1e", *revs)
    hits = []
    for rec in out.split(b"\x1e"):
        parts = rec.strip(b"\n").split(b"\0", 2)
        if len(parts) == 3 and parts[1].decode("utf-8", "replace").lower() in emails and has_watermark(parts[2]):
            hits.append(parts[0].decode())
    return hits


COMMANDS = {b"commit", b"tag", b"reset", b"blob", b"done", b"feature", b"progress", b"checkpoint"}


def _commit_line(word: bytes, line: bytes, mark: str | None, mine: bool, marks: dict, emails: set[str]) -> tuple[str | None, bool]:
    if word == b"mark":
        return line.split()[1].decode(), mine
    if word == b"original-oid" and mark:
        marks[mark] = line.split()[1].decode()
    elif word == b"author":
        found = EMAIL.search(line)
        return mark, bool(found) and found.group(1).decode("utf-8", "replace").lower() in emails
    return mark, mine


def rewrite_stream(stream: bytes, emails: set[str]) -> tuple[bytes, dict[str, str]]:
    """The fast-export stream with attribution removed from the messages of commits by `emails`,
    and each commit mark mapped to its original id."""
    out, marks = [], {}
    i, in_commit, mine, mark = 0, False, False, None
    while i < len(stream):
        end = stream.find(b"\n", i)
        end = len(stream) if end == -1 else end + 1
        line = stream[i:end]
        i = end
        if line.startswith(b"data "):
            n = int(line[5:].strip())
            payload = stream[i:i + n]
            i += n
            if in_commit and mine:
                payload = clean_message(payload)
            out.append(b"data %d\n" % len(payload) + payload)
            continue
        word = line.split(b" ", 1)[0].strip()
        if word in COMMANDS:
            in_commit, mine, mark = word == b"commit", False, None
        elif in_commit:
            mark, mine = _commit_line(word, line, mark, mine, marks, emails)
        out.append(line)
    return b"".join(out), marks


def _headers(raw: bytes) -> tuple[list[bytes], bytes]:
    head, _, msg = raw.partition(b"\n\n")
    kept, in_sig = [], False
    for line in head.split(b"\n"):
        if line.startswith(SIGNATURE):
            in_sig = True
            continue
        if in_sig and line.startswith(b" "):
            continue
        in_sig = False
        if not line.startswith(b"parent "):
            kept.append(line)
    return kept, msg


def verify(repo: Path, pairs: dict[str, str], emails: set[str]) -> int:
    changed = 0
    for old, new in pairs.items():
        if old == new:
            continue
        old_head, old_msg = _headers(_git(repo, "cat-file", "commit", old))
        new_head, new_msg = _headers(_git(repo, "cat-file", "commit", new))
        if old_head != new_head:
            raise Abort(f"{old[:10]} -> {new[:10]} changed more than the message")
        author = next((EMAIL.search(h) for h in old_head if h.startswith(b"author ")), None)
        is_mine = bool(author) and author.group(1).decode("utf-8", "replace").lower() in emails
        if new_msg != (clean_message(old_msg) if is_mine else old_msg):
            raise Abort(f"{old[:10]} -> {new[:10]} message changed beyond the attribution lines")
        changed += new_msg != old_msg
    return changed


def _refs(repo: Path) -> dict[str, str]:
    out = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/tags").decode()
    return dict(line.split(" ", 1) for line in out.splitlines() if line)


def _restore(repo: Path, bundle: Path) -> None:
    _git(repo, "fetch", "-q", "--update-head-ok", str(bundle), "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*")


def _rewrite_revs(repo: Path, gitdir: Path, emails: set[str], revs: tuple[str, ...], expected: int) -> int:
    stream, origin = rewrite_stream(_git(repo, *EXPORT, *revs), emails)
    fd, marks_file = tempfile.mkstemp(prefix="scrub-marks-", dir=gitdir)
    os.close(fd)
    try:
        _git(repo, "fast-import", "--force", "--quiet", f"--export-marks={marks_file}", stdin=stream)
        new = dict(line.split(" ", 1) for line in Path(marks_file).read_text(encoding="ascii").splitlines() if line)
        changed = verify(repo, {origin[m]: new[m].strip() for m in origin if m in new}, emails)
    finally:
        os.unlink(marks_file)
    if changed != expected or attributed(repo, emails, revs):
        raise Abort(f"{expected} commits carried attribution but {changed} changed")
    return changed


def _bundle(repo: Path, gitdir: Path, revs: tuple[str, ...], label: str = "") -> Path:
    stem = f"code-jig-scrub-{time.strftime('%Y%m%d-%H%M%S')}" + (f"-{re.sub(r'[^A-Za-z0-9._-]+', '-', label)}" if label else "")
    bundle, n = gitdir / f"{stem}.bundle", 0
    while bundle.exists():
        n += 1
        bundle = gitdir / f"{stem}-{n}.bundle"
    _git(repo, "bundle", "create", "-q", str(bundle), *revs)
    return bundle


def common_dir(repo: Path) -> Path:
    return (Path(repo) / _git(repo, "rev-parse", "--git-common-dir").decode().strip()).resolve()


def range_revs(branch_ref: str, base: str | None) -> tuple[str, ...]:
    return (branch_ref, *([f"^{base}"] if base else []), "--not", "--remotes")


def blocker(repo: Path, revs: tuple[str, ...], emails: set[str]) -> str | None:
    shas = _git(repo, "rev-list", *revs).decode().split()
    batch = _git(repo, "cat-file", "--batch", stdin="".join(f"{sha}\n" for sha in shas).encode()) if shas else b""
    pos = 0
    for sha in shas:
        nl = batch.index(b"\n", pos)
        size = int(batch[pos:nl].split()[2])
        head = batch[nl + 1:nl + 1 + size].partition(b"\n\n")[0].split(b"\n")
        pos = nl + 2 + size
        if any(h.startswith(SIGNATURE) for h in head):
            return f"{sha[:10]} is signed"
        author = next((EMAIL.search(h) for h in head if h.startswith(b"author ")), None)
        if not author or author.group(1).decode("utf-8", "replace").lower() not in emails:
            return f"{sha[:10]} is by someone else"
    return None


def rewrite(repo: Path, gitdir: Path, emails: set[str], expected: int) -> tuple[int, dict[str, str], Path]:
    before = _refs(repo)
    bundle = _bundle(repo, gitdir, ALL)
    try:
        changed = _rewrite_revs(repo, gitdir, emails, ALL, expected)
    except Abort:
        _restore(repo, bundle)
        raise
    return changed, before, bundle


def rewrite_range(repo: Path, branch_ref: str, base: str | None, emails: set[str]) -> tuple[int, Path | None]:
    revs = range_revs(branch_ref, base)
    expected = len(attributed(repo, emails, revs))
    if not expected:
        return 0, None
    reason = blocker(repo, revs, emails)
    if reason:
        raise Abort(reason)
    gitdir = common_dir(repo)
    old = _git(repo, "rev-parse", "--verify", f"{branch_ref}^{{commit}}").decode().strip()
    bundle = _bundle(repo, gitdir, revs, branch_ref.removeprefix("refs/heads/"))
    try:
        return _rewrite_revs(repo, gitdir, emails, revs, expected), bundle
    except Abort:
        _git(repo, "update-ref", branch_ref, old)
        raise


def _report(repo: Path, before: dict[str, str]) -> list[str]:
    lines = []
    for ref, old in sorted(before.items()):
        if not ref.startswith("refs/heads/"):
            continue
        branch = ref.removeprefix("refs/heads/")
        upstream = _git(repo, "rev-parse", "-q", "--abbrev-ref", f"{branch}@{{upstream}}", check=False).decode().strip()
        if not upstream or "/" not in upstream:
            lines.append(f"  {branch}: no upstream")
            continue
        remote, _, rbranch = upstream.partition("/")
        cmd = ["git", "push", f"--force-with-lease={rbranch}:{old}", remote, f"{branch}:{rbranch}"]
        lines.append(f"  {branch}: {shlex.join(cmd)}")
    return lines


def cli(args) -> int:
    repo = Path(args.path).resolve()
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-common-dir"], capture_output=True, text=True,
                       encoding="utf-8", check=False)
    if r.returncode:
        print(f"code-jig: {repo} is not a git repository", file=sys.stderr)
        return 2
    gitdir = (repo / r.stdout.strip()).resolve()
    emails = my_emails(repo, args.author)
    if not emails:
        print("code-jig: set git config user.email or codejig.email, or pass --author EMAIL", file=sys.stderr)
        return 2
    try:
        hits = attributed(repo, emails)
        if not hits:
            print(f"{repo.name}: clean, no attribution in commits by {', '.join(sorted(emails))}")
            return 0
        print(f"{repo.name}: {len(hits)} commits by {', '.join(sorted(emails))} carry AI attribution")
        if args.dry_run:
            print("\n".join(f"  {h[:10]} {_git(repo, 'log', '-1', '--format=%s', h).decode().strip()}" for h in hits))
            return 0
        changed, before, bundle = rewrite(repo, gitdir, emails, len(hits))
    except Abort as e:
        print(f"code-jig: ABORT, nothing changed: {e}", file=sys.stderr)
        return 1
    print(f"rewrote {changed} commits, message only; trees, authors and dates verified unchanged")
    print(f"backup: {bundle}")
    print("nothing was pushed; to publish each branch, run:")
    print("\n".join(_report(repo, before)))
    return 0
