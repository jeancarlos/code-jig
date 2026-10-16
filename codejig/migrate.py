from __future__ import annotations

import contextlib
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


def _rows(path: Path) -> int:
    with contextlib.closing(sqlite3.connect(path)) as con:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return sum(con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables)


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dst)
    except OSError:
        shutil.copy2(src, dst)
        src.unlink()


def move_db(home: Path, dry_run: bool = False) -> list[str]:
    old, new = old_state(home) / "usage.sqlite3", collect.db_path()
    if not old.is_file():
        return []
    if new.exists() and _rows(new):
        return [f"refused: {new} already has data; move one of them away and rerun"]
    if not dry_run:
        _move(old, new)
    return [f"{'would ' if dry_run else ''}move {old} to {new}"]


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8").stdout
    except OSError:
        return ""


def _config(repo: Path | None, *args: str) -> list[str]:
    scope = ["-C", str(repo), "config", "--local"] if repo else ["config", "--global"]
    return _git(*scope, *args).splitlines()


def _is_work_tree(path: Path) -> bool:
    return _git("-C", str(path), "rev-parse", "--is-inside-work-tree").strip() == "true"


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
            olds = _config(repo, "--get-all", old)
            if not olds:
                continue
            have = _config(repo, "--get-all", new)
            for value in olds:
                if value in have:
                    continue
                have.append(value)
                if not dry_run:
                    _config(repo, "--add", new, value)
                lines.append(f"{p}copy {old} = {value} to {new} ({where})")
            if not dry_run:
                _config(repo, "--unset-all", old)
            lines.append(f"{p}unset {old} ({where})")
    return lines


def release_hooks_path(home: Path, dry_run: bool = False) -> list[str]:
    old = old_state(home) / "git-hooks"
    current = install._git_config("--get", "core.hooksPath")
    if not current or not install._same_path(current, old):
        return []
    if not dry_run:
        install._git_config("--unset", "core.hooksPath")
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
    return 1 if any(line.startswith("refused:") for line in lines) else 0
