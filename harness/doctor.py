from __future__ import annotations

import mmap
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from harness import paths
from harness.install import render_agents
from harness.overlay import Overlay, load

Check = tuple[str, str, str]

PACK_KEYS = (
    "project_doc_max_bytes",
    "approvals_reviewer",
    "model_auto_compact_token_limit",
    "tool_output_token_limit",
)
SHIM_MAX_BYTES = 1_000_000


def resolve_codex_bin(arg: str | None) -> Path | None:
    value = arg or os.environ.get("CODEX_BIN") or shutil.which("codex")
    return Path(value) if value else None


def check_binary(bin_path: Path | None, keys=PACK_KEYS) -> list[Check]:
    name = "codex keys"
    if bin_path is None or not bin_path.is_file():
        return [("FAIL", name, "codex binary not found; pass --codex-bin PATH or set CODEX_BIN")]
    try:
        if bin_path.stat().st_size < SHIM_MAX_BYTES:
            return [("FAIL", name, f"{bin_path} is a launcher, not the native binary; pass --codex-bin PATH")]
        with open(bin_path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
            missing = [k for k in keys if m.find(k.encode()) == -1]
    except OSError as e:
        return [("FAIL", name, f"cannot read {bin_path}: {e.strerror or e}")]
    if missing:
        return [("FAIL", name, f"not in {bin_path.name}: {', '.join(missing)}")]
    return [("ok", name, f"{len(keys)} keys present in {bin_path.name}")]


def report(checks: list[Check]) -> int:
    for level, name, detail in checks:
        print(f"{level} {name}: {detail}")
    return 1 if any(c[0] == "FAIL" for c in checks) else 0


DEFAULT_DOC_MAX = 32768


def _pick(directory: Path) -> Path | None:
    for name in ("AGENTS.override.md", "AGENTS.md"):
        f = directory / name
        if f.is_file() and f.stat().st_size > 0:
            return f
    return None


def _git_root(cwd: Path) -> Path:
    for d in (cwd, *cwd.parents):
        if (d / ".git").exists():
            return d
    return cwd


def chain_files(home: Path, cwd: Path) -> list[Path]:
    files = [f for f in [_pick(home)] if f]
    root = _git_root(cwd)
    dirs = [root, *[d for d in reversed(cwd.parents) if root in d.parents], cwd] if cwd != root else [root]
    seen = set()
    for d in dirs:
        if d in seen:
            continue
        seen.add(d)
        f = _pick(d)
        if f:
            files.append(f)
    return files


def _doc_max(home: Path) -> int:
    cfg = home / "config.toml"
    if not cfg.is_file():
        return DEFAULT_DOC_MAX
    try:
        value = tomllib.loads(cfg.read_text(encoding="utf-8")).get("project_doc_max_bytes", DEFAULT_DOC_MAX)
    except (OSError, ValueError):
        return DEFAULT_DOC_MAX
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_DOC_MAX
    return value


def check_chain(home: Path, cwd: Path) -> list[Check]:
    cap = _doc_max(home)
    total = sum(f.stat().st_size for f in chain_files(home, cwd))
    detail = f"{total} of {cap} bytes"
    if total > cap:
        return [("FAIL", "AGENTS.md chain", detail + "; Codex silently stops adding files past the cap")]
    if total > cap * 0.8:
        return [("warn", "AGENTS.md chain", detail)]
    return [("ok", "AGENTS.md chain", detail)]


def check_global(home: Path, core: Path, ov: Overlay) -> list[Check]:
    name = "global AGENTS.md"
    override = home / "AGENTS.override.md"
    if override.is_file() and override.stat().st_size > 0:
        return [("FAIL", name, f"{override} is non-empty; Codex loads it instead of the generated AGENTS.md")]
    target = home / "AGENTS.md"
    if not target.is_file():
        return [("warn", name, f"{target} is missing; run harness install")]
    if target.read_bytes() != render_agents(core, ov.root).encode("utf-8"):
        return [("warn", name, f"{target} is stale; run harness install")]
    return [("ok", name, f"{target} is current")]


def _git(core: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(core), *args], capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return None


def check_core(core: Path, ov: Overlay) -> list[Check]:
    strict = "FAIL" if not ov.core_writable else "warn"
    described = _git(core, "describe", "--tags", "--exact-match", "HEAD")
    tag = described.stdout.strip() if described and described.returncode == 0 else ""
    status = _git(core, "status", "--porcelain")
    if status is None or status.returncode != 0:
        reason = f"{core} is not a readable git repo or git is missing"
        first = (status.stderr.strip().splitlines() or [""])[0] if status else ""
        if first:
            reason += f": {first}"
        pin = (strict, "core pin", f"cannot be checked; overlay pins {ov.core_version}")
        return [pin, ("FAIL", "core clean", reason)]
    pin = ("ok", "core pin", tag) if tag == ov.core_version else (
        strict, "core pin", f"core is at {tag or 'an untagged commit'}, overlay pins {ov.core_version}")
    dirty = status.stdout.strip()
    clean = ("FAIL", "core clean", "core has local edits but core_writable = false") if dirty and not ov.core_writable \
        else ("ok", "core clean", "local edits allowed" if dirty else "no local edits")
    return [pin, clean]


def cli(args) -> int:
    checks = check_binary(resolve_codex_bin(args.codex_bin))
    if not args.check_binary:
        try:
            ov = load(paths.overlay_dir(args.overlay))
        except ValueError as e:
            checks.append(("FAIL", "overlay", str(e)))
        else:
            checks += check_core(paths.CORE, ov)
            checks += check_global(paths.codex_home(args.codex_home), paths.CORE, ov)
        checks += check_chain(paths.codex_home(args.codex_home), Path.cwd())
    return report(checks)
