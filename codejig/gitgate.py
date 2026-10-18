import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from codejig.scrub import (
    Abort,
    blocker,
    common_dir,
    my_emails,
    range_revs,
    rewrite_range,
)
from codejig.watermark import clean_message, has_watermark, is_binary, strip_file

AGENT_ENV = ("CODEX_THREAD_ID", "CLAUDECODE")
DASHES = {"\u2014": "-", "\u2013": "-", "\u2015": "-"}
PROSE = re.compile(r"(?i)(?:^|/)(?:readme|changelog|changes|history|contributing)(?:\.[^/]*)?$|\.(?:md|mdx|markdown|rst|adoc)$")
NOT_PROSE = re.compile(r"(?:^|/)(?:AGENTS(?:\.override)?\.md|CLAUDE\.md|SKILL\.md)$|(?:^|/)specs?/")
VENDORED = re.compile(r"(?:^|/)(?:node_modules|vendor|dist|\.obsidian)/|\.min\.(?:js|css)$")
HOOK_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")
GATED = ("commit-msg", "pre-commit", "pre-push")
HOOKS = ("applypatch-msg", "pre-applypatch", "post-applypatch", "pre-commit", "pre-merge-commit",
         "prepare-commit-msg", "commit-msg", "post-commit", "pre-rebase", "post-checkout", "post-merge",
         "pre-push", "pre-receive", "update", "post-receive", "post-update", "push-to-checkout",
         "pre-auto-gc", "post-rewrite", "sendemail-validate")


def _git(*args: str, stdin: bytes | None = None, check: bool = True) -> bytes:
    r = subprocess.run(["git", *args], capture_output=True, input=stdin, check=False)
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
        new = undash(clean_message(data))
    except UnicodeDecodeError:
        return 0
    if new != data:
        p.write_bytes(new)
        print("code-jig: cleaned the commit message (AI attribution, dashes)", file=sys.stderr)
    return 0


def is_prose(path: str) -> bool:
    return bool(PROSE.search(path)) and not NOT_PROSE.search(path)


def _fix(data: bytes, path: str) -> tuple[bytes | None, list[int]]:
    if data.isascii() or b"\0" in data[:8192] or is_binary(data):
        return None, []
    cleaned, report = strip_file(data, path)
    if is_prose(path):
        cleaned = undash(cleaned)
    return (cleaned if cleaned != data else None), report["left"]


def _from_agent() -> bool:
    return any(os.environ.get(k) for k in AGENT_ENV)


def _prose_allowed() -> bool:
    return _git("config", "--local", "--bool", "codejig.allowProse", check=False).strip() == b"true"


def _fix_staged(path: str, mode: str, sha: str) -> tuple[bool, list[int]]:
    new, left = _fix(_git("cat-file", "blob", sha), path)
    if new is not None:
        blob = _git("hash-object", "-w", "--no-filters", "--stdin", stdin=new).decode().strip()
        _git("update-index", "--cacheinfo", f"{mode},{blob},{path}")
    work = Path(path)
    if work.is_file() and not work.is_symlink() and os.path.realpath(work) == os.path.join(os.path.realpath("."), os.path.normpath(path)):
        fixed, _ = _fix(work.read_bytes(), path)
        if fixed is not None:
            work.write_bytes(fixed)
    return new is not None, left


def _staged() -> list[tuple[str, str, str]]:
    """(path, mode, blob) of every added, modified or type-changed regular file, renames counted as additions.

    Read from one raw diff, so a file name is never interpreted as a pathspec."""
    fields = _git("diff", "--cached", "--raw", "-z", "--no-renames", "--no-abbrev", "--diff-filter=AMT").split(b"\0")
    out = []
    for meta, path in zip(fields[0::2], fields[1::2], strict=False):
        parts = meta.decode().lstrip(":").split()
        if len(parts) == 5 and parts[1] in ("100644", "100755"):
            out.append((os.fsdecode(path), parts[1], parts[3]))
    return out


def pre_commit(prose: bool) -> int:
    staged = _staged()
    prose_files = [path for path, _, _ in staged if is_prose(path)]
    fixed, unsure = [], []
    for path, mode, sha in staged:
        if not VENDORED.search(path):
            changed, left = _fix_staged(path, mode, sha)
            fixed += [path] if changed else []
            unsure += [f"{path}:{n}" for n in left]
    if fixed:
        print(f"code-jig: replaced invisible characters in {', '.join(fixed)}", file=sys.stderr)
    agent, code = _from_agent(), 0
    if unsure:
        print(f"code-jig: {'refusing to commit' if agent else 'left'} invisible characters that may be meant in code "
              "or data (a string literal, a fixture):", file=sys.stderr)
        for spot in unsure:
            print(f"  {spot}", file=sys.stderr)
        if agent:
            print("Write each one as an escape (such as \\u200b) or delete it, then stage the file again.", file=sys.stderr)
            code = 1
    if prose and prose_files and agent and not _prose_allowed():
        print("code-jig: refusing to commit prose written in an agent session:", file=sys.stderr)
        for path in prose_files:
            print(f"  {path}", file=sys.stderr)
        print("Unstage these files (git restore --staged <file>) and commit the rest; the user reviews and commits "
              "the prose. A repo where agents may commit prose: git config codejig.allowProse true",
              file=sys.stderr)
        code = 1
    return code


def _null_sha(sha: str) -> bool:
    return not sha.strip("0")


def _known(remote: str) -> bool:
    return not _null_sha(remote) and subprocess.run(["git", "cat-file", "-e", f"{remote}^{{commit}}"], capture_output=True, check=False).returncode == 0


def _outgoing(local: str, remote: str) -> list[str]:
    spec = [f"{remote}..{local}"] if _known(remote) else [local, "--not", "--remotes"]
    return _git("rev-list", *spec).decode().split()


def _cleanup_on(default: bool) -> bool:
    value = _git("config", "--bool", "--get", "codejig.pushCleanup", check=False).strip()
    return {b"true": True, b"false": False}.get(value, default)


def _base(remote: str) -> str | None:
    return remote if _known(remote) else None


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _rebasing(ref: str) -> bool:
    common = common_dir(Path.cwd())
    for gitdir in [common, *common.glob("worktrees/*")]:
        merge, apply = gitdir / "rebase-merge", gitdir / "rebase-apply"
        busy = [_read(merge / "head-name"), _read(apply / "head-name"), *_read(merge / "update-refs").splitlines()]
        if (apply / "applying").exists():
            busy.append(_read(gitdir / "HEAD").strip().removeprefix("ref: "))
        if ref in (b.strip() for b in busy):
            return True
    return False


def _unpushed(shas: list[str]) -> set[str]:
    return set(_git("rev-list", *shas, "--not", "--remotes").decode().split())


def _cleanable(ref: str, local: str, remote: str, bad: list[str], emails: set[str]) -> bool:
    if not ref.startswith("refs/heads/") or _git("rev-parse", "-q", "--verify", ref, check=False).decode().strip() != local:
        return False
    if _rebasing(ref) or not set(bad) <= _unpushed(bad):
        return False
    return blocker(Path.cwd(), range_revs(ref, _base(remote)), emails) is None


def _clean(branches: dict[str, tuple[str, str, list[str]]], emails: set[str]) -> bool:
    done, notes = {}, []
    try:
        for ref, (local, remote, _) in branches.items():
            done[ref] = local
            n, bundle = rewrite_range(Path.cwd(), ref, _base(remote), emails)
            notes.append(f"code-jig: cleaned AI attribution from {n} commits on {ref.removeprefix('refs/heads/')}; "
                         f"backup {bundle}; run the same push again")
    except Abort as e:
        for ref, old in done.items():
            _git("update-ref", ref, old)
        print(f"code-jig: cleanup aborted, nothing changed: {e}", file=sys.stderr)
        return False
    print("\n".join(notes), file=sys.stderr)
    return True


def _bad_commits(local: str, remote: str, emails: set[str]) -> list[str]:
    bad = []
    for sha in _outgoing(local, remote):
        email, _, body = _git("log", "-1", "--format=%ae%x00%B", sha).partition(b"\0")
        if email.decode("utf-8", "replace").lower() in emails and has_watermark(body):
            bad.append(sha)
    return bad


def _push_ref(ref: str) -> str:
    if ref == "HEAD":
        return _git("symbolic-ref", "-q", "HEAD", check=False).decode().strip() or ref
    return ref


def _collect_problems(lines: list[str], emails: set[str]) -> tuple[list[str], dict]:
    problems, branches = [], {}
    for parts in (line.split() for line in lines):
        if len(parts) != 4 or _null_sha(parts[1]):
            continue
        if not emails:
            raise RuntimeError("no identity to check: set git config user.email (or codejig.email)")
        bad = _bad_commits(parts[1], parts[3], emails)
        if bad:
            problems += bad
            branches[_push_ref(parts[0])] = (parts[1], parts[3], bad)
    return problems, branches


def _refuse(problems: list[str]) -> int:
    shas = list(dict.fromkeys(problems))
    local = _unpushed(shas)
    print("code-jig: push refused, commit messages carry AI attribution:", file=sys.stderr)
    for sha in shas:
        lock = "" if sha in local else " [locked: already on a remote]"
        print(f"  {sha[:10]} {_git('log', '-1', '--format=%s', sha).decode().strip()}{lock}", file=sys.stderr)
    if any(sha not in local for sha in shas):
        print("Locked commits are already upstream, so code-jig never rewrites them. Fixing one rewrites shared history, "
              "which only you decide: reword it by hand (git rebase -i <sha>^, mark it reword), then push with "
              "--force-with-lease.", file=sys.stderr)
    if local & set(shas):
        print("Commits not on any remote yet: push the branch itself, not a tag or a SHA, with push cleanup on "
              "(git config codejig.pushCleanup true) and the gate cleans them; or reword them yourself "
              "(git commit --amend for the last one, git rebase -i for older ones).", file=sys.stderr)
    return 1


def pre_push(lines: list[str], cleanup: bool = False) -> int:
    emails = my_emails(Path.cwd())
    problems, branches = _collect_problems(lines, emails)
    if not problems:
        return _run_tests()
    if _cleanup_on(cleanup) and all(_cleanable(ref, local, remote, bad, emails)
                                    for ref, (local, remote, bad) in branches.items()) and _clean(branches, emails):
        return 1
    return _refuse(problems)


def _run_tests() -> int:
    cmd = _git("config", "--get", "codejig.testCommand", check=False).decode("utf-8", "replace").strip()
    if not cmd:
        return 0
    if os.environ.get("CODE_JIG_SKIP_TESTS") == "1":
        print("code-jig: CODE_JIG_SKIP_TESTS=1, skipping the pre-push tests", file=sys.stderr)
        return 0
    try:
        top = _git("rev-parse", "--show-toplevel").decode("utf-8", "replace").strip()
    except RuntimeError:
        top = ""
    if not top:
        print("code-jig: push refused, cannot find the repo top level to run tests", file=sys.stderr)
        return 1
    env = {k: v for k, v in os.environ.items() if k not in HOOK_GIT_ENV}
    rc = subprocess.run(cmd, shell=True, cwd=top, env=env, check=False).returncode
    if rc:
        print(f"code-jig: push refused, tests fail ({cmd} exited {rc})", file=sys.stderr)
        return 1
    return 0


def shims(lib: Path, python: str, prose: bool, cleanup: bool = False) -> dict[str, str]:
    """One POSIX shell hook per git hook name: the gate for the gated ones, then the repo's own hook."""
    run = f"PYTHONPATH={shlex.quote(Path(lib).as_posix())} {shlex.quote(Path(python).as_posix())} -P -s -m codejig git-hook"
    local = 'dir="$(git rev-parse --git-common-dir 2>/dev/null)/hooks"'
    out = {}
    for name in HOOKS:
        if name == "pre-push":
            body = (f'input=$(cat)\nprintf \'%s\\n\' "$input" | {run}{" --cleanup" if cleanup else ""} pre-push "$@" || exit 1\n{local}\n'
                    f'[ -x "$dir/{name}" ] && {{ printf \'%s\\n\' "$input" | "$dir/{name}" "$@"; exit $?; }}\nexit 0\n')
        else:
            flag = " --prose" if name == "pre-commit" and prose else ""
            gate = f'{run}{flag} {name} "$@" || exit 1\n' if name in GATED else ""
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
            return pre_push(sys.stdin.read().splitlines(), args.cleanup)
    except Exception as e:
        what = "push" if args.name == "pre-push" else "commit"
        print(f"code-jig: {what} refused, the {args.name} gate could not finish: {e}", file=sys.stderr)
        return 1
    return 0
