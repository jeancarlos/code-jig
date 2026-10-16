from __future__ import annotations

import contextlib
import errno
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from codejig import collect, install, paths
from codejig.overlay import Overlay, load

NOTICE = "code-jig migrate is deprecated and will be removed in the next release"
KEYS = ("email", "allowProse")


def old_state(home: Path) -> Path:
    return home / "codex-harness"


def _has_rows(path: Path) -> bool:
    try:
        with contextlib.closing(sqlite3.connect(path)) as con:
            tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
            return any(con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables)
    except sqlite3.DatabaseError:
        return True


def _move(src: Path, dst: Path) -> str | None:
    in_use = f"refused: {src} is in use; close Codex and Claude Code and rerun"
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dst)
        return None
    except PermissionError:
        return in_use
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
    tmp = dst.with_name(dst.name + ".migrate-tmp")
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    try:
        src.unlink()
    except OSError:
        dst.unlink()
        return in_use
    return None


def move_db(home: Path, dry_run: bool = False) -> list[str]:
    old, new = old_state(home) / "usage.sqlite3", collect.db_path()
    if not old.is_file():
        return []
    if old.with_name(old.name + "-journal").exists():
        return [f"refused: {old} has an unfinished write; open and close Codex once and rerun"]
    if new.exists() and _has_rows(new):
        return [f"refused: {new} already has data; move one of them away and rerun"]
    if not dry_run:
        refused = _move(old, new)
        if refused:
            return [refused]
    return [f"{'would ' if dry_run else ''}move {old} to {new}"]


def _git(*args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return None


def _config(repo: Path | None, *args: str) -> subprocess.CompletedProcess | None:
    scope = ["-C", str(repo), "config", "--local"] if repo else ["config", "--global"]
    return _git(*scope, *args)


def _values(repo: Path | None, key: str) -> list[str]:
    r = _config(repo, "--get-all", "-z", key)
    return r.stdout.split("\0")[:-1] if r and r.returncode == 0 else []


def _write(repo: Path | None, *args: str) -> str | None:
    r = _config(repo, *args)
    if r and r.returncode == 0:
        return None
    why = r.stderr.strip() if r else "git not found"
    return f"failed: git config {' '.join(args)} ({'global' if repo is None else repo}): {why}"


def _is_work_tree(path: Path) -> bool:
    r = _git("-C", str(path), "rev-parse", "--is-inside-work-tree")
    return bool(r) and r.stdout.strip() == "true"


def default_repos() -> list[Path]:
    return [Path.cwd()] if _is_work_tree(Path.cwd()) else []


def move_git_config(repos: list[Path], dry_run: bool = False) -> list[str]:
    lines = []
    p = "would " if dry_run else ""
    for repo in [None, *repos]:
        if repo is not None and not _is_work_tree(repo):
            lines.append(f"skip {repo}: not a git repo")
            continue
        where = "global" if repo is None else str(repo)
        for key in KEYS:
            old, new = f"codexharness.{key}", f"codejig.{key}"
            olds = _values(repo, old)
            if not olds:
                continue
            have = _values(repo, new)
            for value in olds:
                if value in have:
                    continue
                if dry_run:
                    have.append(value)
                    lines.append(f"{p}copy {old} = {value} to {new} ({where})")
                    continue
                failed = _write(repo, "--add", new, value)
                lines.append(failed or f"copy {old} = {value} to {new} ({where})")
            if not dry_run:
                if not set(olds) <= set(_values(repo, new)):
                    lines.append(f"failed: kept {old} ({where}) because {new} does not hold every value")
                    continue
                failed = _write(repo, "--unset-all", old)
                if failed:
                    lines.append(failed)
                    continue
            lines.append(f"{p}unset {old} ({where})")
    return lines


def release_hooks_path(home: Path, dry_run: bool = False) -> list[str]:
    old = old_state(home) / "git-hooks"
    current = install._git_config("--get", "core.hooksPath")
    if not current or not install._same_path(current, old):
        return []
    failed = None if dry_run else _write(None, "--unset", "core.hooksPath")
    if failed:
        return [failed]
    return [f"{'would ' if dry_run else ''}unset core.hooksPath {current}"]


def run(core: Path, ov: Overlay, home: Path, repos: list[Path], dry_run: bool) -> list[str]:
    return [*move_db(home, dry_run), *move_git_config(repos, dry_run), *release_hooks_path(home, dry_run)]


def cli(args) -> int:
    print(NOTICE)
    try:
        ov = load(paths.overlay_dir(args.overlay))
    except ValueError as e:
        print(f"code-jig: {e}", file=sys.stderr)
        return 2
    repos = [Path(r) for r in args.repos] if args.repos else default_repos()
    lines = run(paths.CORE, ov, paths.codex_home(args.codex_home), repos, args.dry_run)
    for line in lines:
        print(line)
    return 1 if any(line.startswith(("refused:", "failed:")) for line in lines) else 0
