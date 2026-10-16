import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from codejig.scrub import my_emails, scrub_message
from codejig.watermark import ATTRIBUTION_LINES, is_binary, strip_bytes

ZERO = "0" * 40
AGENT_ENV = ("CODEX_THREAD_ID", "CLAUDECODE")
DASHES = {"\u2014": "-", "\u2013": "-", "\u2015": "-"}
PROSE = re.compile(r"(?i)(?:^|/)(?:readme|changelog|changes|history|contributing)(?:\.[^/]*)?$|\.(?:md|mdx|markdown|rst|adoc)$")
NOT_PROSE = re.compile(r"(?:^|/)(?:AGENTS(?:\.override)?\.md|CLAUDE\.md|SKILL\.md)$|(?:^|/)specs?/")
VENDORED = re.compile(r"(?:^|/)(?:node_modules|vendor|dist|\.obsidian)/|\.min\.(?:js|css)$")
GATED = ("commit-msg", "pre-commit", "pre-push")
HOOKS = ("applypatch-msg", "pre-applypatch", "post-applypatch", "pre-commit", "pre-merge-commit",
         "prepare-commit-msg", "commit-msg", "post-commit", "pre-rebase", "post-checkout", "post-merge",
         "pre-push", "pre-receive", "update", "post-receive", "post-update", "push-to-checkout",
         "pre-auto-gc", "post-rewrite", "sendemail-validate")


def _git(*args: str, stdin: bytes | None = None, check: bool = True) -> bytes:
    r = subprocess.run(["git", *args], capture_output=True, input=stdin)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def undash(data: bytes) -> bytes:
    text = data.decode("utf-8")
    for dash, plain in DASHES.items():
        text = text.replace(dash, plain)
    return text.encode("utf-8")


def commit_msg(path: str) -> int:
    p = Path(path)
    data = p.read_bytes()
    try:
        new = undash(scrub_message(data))
    except UnicodeDecodeError:
        return 0
    if new != data:
        p.write_bytes(new)
        print("code-jig: cleaned the commit message (AI attribution, dashes)", file=sys.stderr)
    return 0


def is_prose(path: str) -> bool:
    return bool(PROSE.search(path)) and not NOT_PROSE.search(path)


def _fix(data: bytes, path: str) -> bytes | None:
    if data.isascii() or b"\0" in data[:8192] or is_binary(data):
        return None
    cleaned, _ = strip_bytes(data, attribution=False)
    if is_prose(path):
        cleaned = undash(cleaned)
    return cleaned if cleaned != data else None


def _from_agent() -> bool:
    return any(os.environ.get(k) for k in AGENT_ENV)


def _prose_allowed() -> bool:
    return _git("config", "--local", "--bool", "codejig.allowProse", check=False).strip() == b"true"


def _fix_staged(path: str, mode: str, sha: str) -> bool:
    new = _fix(_git("cat-file", "blob", sha), path)
    if new is not None:
        blob = _git("hash-object", "-w", "--no-filters", "--stdin", stdin=new).decode().strip()
        _git("update-index", "--cacheinfo", f"{mode},{blob},{path}")
    work = Path(path)
    if work.is_file() and not work.is_symlink():
        fixed = _fix(work.read_bytes(), path)
        if fixed is not None:
            work.write_bytes(fixed)
    return new is not None


def _staged() -> list[tuple[str, str, str]]:
    """(path, mode, blob) of every added or modified regular file, renames counted as additions.

    Read from one raw diff, so a file name is never interpreted as a pathspec."""
    fields = _git("diff", "--cached", "--raw", "-z", "--no-renames", "--no-abbrev", "--diff-filter=AM").split(b"\0")
    out = []
    for meta, path in zip(fields[0::2], fields[1::2]):
        parts = meta.decode().lstrip(":").split()
        if len(parts) == 5 and parts[1] in ("100644", "100755"):
            out.append((os.fsdecode(path), parts[1], parts[3]))
    return out


def pre_commit(prose: bool) -> int:
    staged = _staged()
    prose_files = [path for path, _, _ in staged if is_prose(path)]
    fixed = [path for path, mode, sha in staged if not VENDORED.search(path) and _fix_staged(path, mode, sha)]
    if fixed:
        print(f"code-jig: replaced invisible characters in {', '.join(fixed)}", file=sys.stderr)
    if prose and prose_files and _from_agent() and not _prose_allowed():
        print("code-jig: refusing to commit prose written in an agent session:", file=sys.stderr)
        for path in prose_files:
            print(f"  {path}", file=sys.stderr)
        print("Unstage these files (git restore --staged <file>) and commit the rest; the user reviews and commits "
              "the prose. A repo where agents may commit prose: git config codejig.allowProse true",
              file=sys.stderr)
        return 1
    return 0


def _outgoing(local: str, remote: str) -> list[str]:
    known = remote != ZERO and subprocess.run(["git", "cat-file", "-e", f"{remote}^{{commit}}"], capture_output=True).returncode == 0
    spec = [f"{remote}..{local}"] if known else [local, "--not", "--remotes"]
    return _git("rev-list", "--no-merges", *spec).decode().split()


def pre_push(lines: list[str]) -> int:
    emails = my_emails(Path.cwd())
    problems = []
    for line in lines:
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:
            continue
        for sha in _outgoing(parts[1], parts[3]):
            email, _, body = _git("log", "-1", "--format=%ae%x00%B", sha).partition(b"\0")
            if email.decode("utf-8", "replace").lower() in emails and ATTRIBUTION_LINES.search(body):
                problems.append(sha)
    if problems:
        print("code-jig: push refused, commit messages carry AI attribution:", file=sys.stderr)
        for sha in dict.fromkeys(problems):
            print(f"  {sha[:10]} {_git('log', '-1', '--format=%s', sha).decode().strip()}", file=sys.stderr)
        print("Remove it with: code-jig scrub (rewrites messages only, then prints the push commands)", file=sys.stderr)
        return 1
    return 0


def shims(lib: Path, python: str, prose: bool) -> dict[str, str]:
    """One POSIX shell hook per git hook name: the gate for the gated ones, then the repo's own hook."""
    run = f"PYTHONPATH={shlex.quote(Path(lib).as_posix())} {shlex.quote(Path(python).as_posix())} -P -s -m codejig git-hook"
    local = 'dir="$(git rev-parse --git-common-dir 2>/dev/null)/hooks"'
    out = {}
    for name in HOOKS:
        if name == "pre-push":
            body = (f'input=$(cat)\nprintf \'%s\\n\' "$input" | {run} pre-push "$@" || exit 1\n{local}\n'
                    f'[ -x "$dir/{name}" ] && {{ printf \'%s\\n\' "$input" | "$dir/{name}" "$@"; exit $?; }}\nexit 0\n')
        else:
            flag = " --prose" if name == "pre-commit" and prose else ""
            gate = f'{run} {name}{flag} "$@" || exit 1\n' if name in GATED else ""
            body = f'{gate}{local}\n[ -x "$dir/{name}" ] && exec "$dir/{name}" "$@"\nexit 0\n'
        out[name] = "#!/bin/sh\n" + body
    return out


def cli(args) -> int:
    try:
        if args.name == "commit-msg" and args.rest:
            return commit_msg(args.rest[0])
        if args.name == "pre-commit":
            return pre_commit(args.prose)
        if args.name == "pre-push":
            return pre_push(sys.stdin.read().splitlines())
    except (OSError, RuntimeError) as e:
        print(f"code-jig: git hook {args.name} skipped: {e}", file=sys.stderr)
    return 0
