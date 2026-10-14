import mmap
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from harness import paths
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
    if bin_path.stat().st_size < SHIM_MAX_BYTES:
        return [("FAIL", name, f"{bin_path} is a launcher, not the native binary; pass --codex-bin PATH")]
    with open(bin_path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
        missing = [k for k in keys if m.find(k.encode()) == -1]
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
    if cfg.is_file():
        try:
            return int(tomllib.loads(cfg.read_text(encoding="utf-8")).get("project_doc_max_bytes", DEFAULT_DOC_MAX))
        except (tomllib.TOMLDecodeError, ValueError):
            return DEFAULT_DOC_MAX
    return DEFAULT_DOC_MAX


def check_chain(home: Path, cwd: Path) -> list[Check]:
    cap = _doc_max(home)
    total = sum(f.stat().st_size for f in chain_files(home, cwd))
    detail = f"{total} of {cap} bytes"
    if total > cap:
        return [("FAIL", "AGENTS.md chain", detail + "; Codex silently stops adding files past the cap")]
    if total > cap * 0.8:
        return [("warn", "AGENTS.md chain", detail)]
    return [("ok", "AGENTS.md chain", detail)]


def _git(core: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(core), *args], capture_output=True, text=True, encoding="utf-8")


def check_core(core: Path, ov: Overlay) -> list[Check]:
    strict = "FAIL" if not ov.core_writable else "warn"
    tag = _git(core, "describe", "--tags", "--exact-match", "HEAD").stdout.strip()
    pin = ("ok", "core pin", tag) if tag == ov.core_version else (
        strict, "core pin", f"core is at {tag or 'an untagged commit'}, overlay pins {ov.core_version}")
    dirty = _git(core, "status", "--porcelain").stdout.strip()
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
        checks += check_chain(paths.codex_home(args.codex_home), Path.cwd())
    return report(checks)
