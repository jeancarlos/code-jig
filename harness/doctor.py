from __future__ import annotations

import json
import mmap
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from harness import managed, paths, probe, tiers
from harness.install import render_agents, render_profile
from harness.overlay import Overlay, load

Check = tuple[str, str, str]

PACK_KEYS = (
    "project_doc_max_bytes",
    "approvals_reviewer",
    "model_auto_compact_token_limit",
    "tool_output_token_limit",
    "model_reasoning_effort",
    "extra_policy",
    "allowed_approvals_reviewers",
    "ignore_rules",
    "allow_managed_hooks_only",
    "guardian_extra_policy",
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


def read_config(home: Path) -> dict:
    try:
        return tomllib.loads((home / "config.toml").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def _doc_max(home: Path) -> int:
    value = read_config(home).get("project_doc_max_bytes", DEFAULT_DOC_MAX)
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


def catalog(home: Path) -> dict[str, set[str]] | None:
    try:
        data = json.loads((home / "models_cache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return None
    out = {}
    for m in models:
        if isinstance(m, dict) and isinstance(m.get("slug"), str):
            levels = m.get("supported_reasoning_levels")
            out[m["slug"]] = {lv.get("effort") for lv in levels if isinstance(lv, dict)} if isinstance(levels, list) else set()
    return out


def family(slug: str) -> str:
    return slug.rsplit("-", 1)[0]


def check_tiers(home: Path, core: Path, ov: Overlay) -> list[Check]:
    try:
        ts = tiers.load(core, ov.root)
    except ValueError as e:
        return [("FAIL", "tiers", str(e))]
    checks: list[Check] = []
    cfg = read_config(home)
    profiles = cfg.get("profiles") if isinstance(cfg.get("profiles"), dict) else {}
    legacy = [t.name for t in ts if cfg.get("profile") == t.name or t.name in profiles]
    checks.append(("FAIL", "legacy profiles", f"{home / 'config.toml'} has profile = or [profiles.*] for {', '.join(legacy)}; Codex refuses --profile with them")
                  if legacy else ("ok", "legacy profiles", "none"))
    policy = tiers.extra_policy(ov.root)
    for t in ts:
        f = home / f"{t.name}.config.toml"
        name = f"tier {t.name} profile"
        if not f.is_file():
            checks.append(("warn", name, f"{f} is missing; Codex silently uses the base config; run harness install"))
        elif f.read_bytes() != render_profile(t, policy).encode("utf-8"):
            checks.append(("warn", name, f"{f} is stale or edited; run harness install"))
        else:
            checks.append(("ok", name, f"{t.model} at {t.effort}"))
    cat = catalog(home)
    if cat is None:
        checks.append(("warn", "model catalog", f"{home / 'models_cache.json'} missing or unreadable; start codex once"))
    else:
        for t in ts:
            name = f"tier {t.name} model"
            if t.model not in cat:
                checks.append(("FAIL", name, f"{t.model} is not in this account's catalog; candidates: {', '.join(sorted(cat))}"))
            elif cat[t.model] and t.effort not in cat[t.model]:
                checks.append(("FAIL", name, f"{t.model} does not support {t.effort}; supported: {', '.join(sorted(cat[t.model]))}"))
            else:
                checks.append(("ok", name, f"{t.model} supports {t.effort}"))
    by = {t.name: t for t in ts}
    if "review" in by and "default" in by:
        same = family(by["review"].model) == family(by["default"].model)
        checks.append(("warn", "review family", f"review and default are both {family(by['default'].model)}; cross-family review catches different bugs")
                      if same else ("ok", "review family", f"{by['review'].model} vs {by['default'].model}"))
    return checks


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
    bin_path = resolve_codex_bin(args.codex_bin)
    home = paths.codex_home(args.codex_home)
    checks = check_binary(bin_path)
    if not args.check_binary:
        try:
            ov = load(paths.overlay_dir(args.overlay))
        except ValueError as e:
            checks.append(("FAIL", "overlay", str(e)))
        else:
            checks += check_core(paths.CORE, ov)
            checks += check_global(home, paths.CORE, ov)
            checks += check_tiers(home, paths.CORE, ov)
            try:
                ts = tiers.load(paths.CORE, ov.root)
            except ValueError:
                ts = []
            checks += managed.check_requirements(managed.requirements_path(), paths.CORE / "bench" / "requirements.toml", ts)
            checks += probe.check_prompt(bin_path, home, Path.cwd(), ts)
            if args.live:
                checks += probe.check_live(bin_path, home, Path.cwd(), ts)
        checks += check_chain(home, Path.cwd())
    return report(checks)
