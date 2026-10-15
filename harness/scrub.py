import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from harness.watermark import ATTRIBUTION_LINES

EXPORT = ["fast-export", "--branches", "--tags", "--no-data", "--show-original-ids", "--reencode=no",
          "--signed-tags=strip", "--tag-of-filtered-object=rewrite"]
SIGNATURE = (b"gpgsig ", b"gpgsig-sha256 ")
EMAIL = re.compile(rb"<([^>]*)>")


class Abort(Exception):
    pass


def _git(repo: Path, *args: str, stdin: bytes | None = None, check: bool = True) -> bytes:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, input=stdin)
    if check and r.returncode:
        raise Abort(f"git {' '.join(args)} failed: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def my_emails(repo: Path, extra: list[str] = ()) -> set[str]:
    """user.email, every codexharness.email value, and `extra`, lower-cased."""
    found = []
    for key in ("user.email", "codexharness.email"):
        r = subprocess.run(["git", "-C", str(repo), "config", "--get-all", key], capture_output=True, text=True)
        found += r.stdout.split()
    return {e.lower() for e in [*found, *extra] if e}


def scrub_message(msg: bytes) -> bytes:
    new = ATTRIBUTION_LINES.sub(b"", msg)
    return msg if new == msg else new.rstrip(b"\n") + b"\n"


def attributed(repo: Path, emails: set[str]) -> list[str]:
    out = _git(repo, "log", "--branches", "--tags", "--format=%H%x00%ae%x00%B%x1e")
    hits = []
    for rec in out.split(b"\x1e"):
        parts = rec.strip(b"\n").split(b"\0", 2)
        if len(parts) == 3 and parts[1].decode("utf-8", "replace").lower() in emails and ATTRIBUTION_LINES.search(parts[2]):
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
                payload = scrub_message(payload)
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
        if new_msg != (scrub_message(old_msg) if is_mine else old_msg):
            raise Abort(f"{old[:10]} -> {new[:10]} message changed beyond the attribution lines")
        changed += new_msg != old_msg
    return changed


def _refs(repo: Path) -> dict[str, str]:
    out = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/tags").decode()
    return dict(line.split(" ", 1) for line in out.splitlines() if line)


def _restore(repo: Path, bundle: Path) -> None:
    _git(repo, "fetch", "-q", "--update-head-ok", str(bundle), "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*")


def rewrite(repo: Path, gitdir: Path, emails: set[str], expected: int) -> tuple[int, dict[str, str], Path]:
    before = _refs(repo)
    bundle = gitdir / f"codex-harness-scrub-{time.strftime('%Y%m%d-%H%M%S')}.bundle"
    _git(repo, "bundle", "create", "-q", str(bundle), "--branches", "--tags")
    stream, origin = rewrite_stream(_git(repo, *EXPORT), emails)
    fd, marks_file = tempfile.mkstemp(prefix="scrub-marks-", dir=gitdir)
    os.close(fd)
    try:
        _git(repo, "fast-import", "--force", "--quiet", f"--export-marks={marks_file}", stdin=stream)
        new = dict(line.split(" ", 1) for line in Path(marks_file).read_text(encoding="ascii").splitlines() if line)
        changed = verify(repo, {origin[m]: new[m].strip() for m in origin if m in new}, emails)
        if changed != expected or attributed(repo, emails):
            raise Abort(f"{expected} commits carried attribution but {changed} changed")
    except Abort:
        _restore(repo, bundle)
        raise
    finally:
        os.unlink(marks_file)
    return changed, before, bundle


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
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"], capture_output=True, text=True)
    if r.returncode:
        print(f"harness: {repo} is not a git repository", file=sys.stderr)
        return 2
    gitdir = Path(r.stdout.strip())
    emails = my_emails(repo, args.author)
    if not emails:
        print("harness: set git config user.email or codexharness.email, or pass --author EMAIL", file=sys.stderr)
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
        print(f"harness: ABORT, nothing changed: {e}", file=sys.stderr)
        return 1
    print(f"rewrote {changed} commits, message only; trees, authors and dates verified unchanged")
    print(f"backup: {bundle}")
    print("nothing was pushed; to publish each branch, run:")
    print("\n".join(_report(repo, before)))
    return 0
