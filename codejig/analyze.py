# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path, PureWindowsPath

from codejig import unsafe_scan

CATEGORIES = ("security", "secret", "dependency", "bug", "type", "unused", "complexity", "duplication")
TOOL_ENV = {"SEMGREP_SEND_METRICS": "off", "SEMGREP_ENABLE_VERSION_CHECK": "0", "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_NOLOGO": "1", "KIOTA_CLI_TELEMETRY_OPTOUT": "1", "PYTHONUTF8": "1"}
COGNITIVE, CYCLOMATIC, NLOC, PARAMS = 15, 15, 100, 7
CODE_SUFFIXES = {".py", ".cs", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".java", ".kt", ".go", ".rs", ".swift", ".php", ".rb", ".scala", ".lua", ".c", ".cc", ".cpp", ".h", ".hpp", ".m"}
SKIP_DIRS = {".git", "node_modules", "bin", "obj", ".venv", "venv", "dist", "build", "__pycache__", "coverage", "htmlcov", ".nyc_output", "target", "vendor"}
ESLINT_COMPLEXITY = {"complexity", "max-depth", "max-lines-per-function", "max-params", "max-nested-callbacks",
                     "sonarjs/cognitive-complexity", "sonarjs/cyclomatic-complexity", "sonarjs/nested-control-flow"}
ESLINT_SECURITY = {f"sonarjs/{r}" for r in (
    "code-eval", "cookie-no-httponly", "cors", "csrf", "encryption-secure-mode", "file-permissions", "hardcoded-secret-signatures",
    "hashing", "insecure-cookie", "no-clear-text-protocols", "no-hardcoded-ip", "no-hardcoded-passwords", "no-hardcoded-secrets",
    "no-ip-forward", "no-os-command-from-path", "no-unsafe-unzip")}
DOTNET_COMPLEXITY = {"S3776", "S1541", "S138", "S107", "CA1502", "CA1505", "CA1506"}
DOTNET_SECURITY = {"CA2100", "S2068", "S2077", "S2245", "S3649", "S4423", "S4426", "S4433", "S4507", "S4790",
                   "S5332", "S5344", "S5443", "S5542", "S5547", "S5659", "S5773", "S6418"}
MSBUILD = re.compile(r"^(.+?)\((\d+),\d+\): (warning|error) ([A-Za-z]+\d+): (.*?)(?: \[[^\]]*\])?$")
MSBUILD_PROJECT = re.compile(r"^(.+?) : (warning|error) ([A-Za-z]+\d+): (.*?)(?: \[[^\]]*\])?$")
VULTURE = re.compile(r"^(.+?):(\d+): (.+?) \((\d+)% confidence[^)]*\)$")
KNIP_UNUSED = ("files", "dependencies", "devDependencies", "optionalPeerDependencies", "exports", "types", "nsExports", "nsTypes",
               "enumMembers", "namespaceMembers", "duplicates", "catalog", "catalogReferences")
KNIP_BROKEN = ("unlisted", "unresolved", "binaries", "cycles")
MYPY = re.compile(r"^(.+?):(\d+)(?::\d+)*: error: (.*?)(?:  \[([\w-]+)\])?$")
DUP_LOC = re.compile(r"^(.+):(\d+) ~ (\d+)$")
GO_POSN = re.compile(r"^(.+):(\d+):\d+$")
CLIPPY_PANIC = {f"clippy::{n}" for n in (
    "unwrap_used", "expect_used", "panic", "todo", "unimplemented", "unreachable", "indexing_slicing", "dbg_macro", "mem_forget",
    "cast_possible_truncation", "cast_sign_loss", "arithmetic_side_effects")}
CLIPPY_UNSAFE = {f"clippy::{n}" for n in (
    "undocumented_unsafe_blocks", "missing_safety_doc", "not_unsafe_ptr_arg_deref", "multiple_unsafe_ops_per_block", "transmute_undefined_repr")}
CLIPPY_COMPLEXITY = {"clippy::cognitive_complexity", "clippy::too_many_arguments", "clippy::too_many_lines", "clippy::type_complexity",
                     "clippy::excessive_nesting"}
PMD_COMPLEXITY = {"CyclomaticComplexity", "CognitiveComplexity", "NPathComplexity", "ExcessiveParameterList", "ExcessiveMethodLength",
                  "NcssCount", "GodClass", "TooManyFields", "TooManyMethods", "AvoidDeeplyNestedIfStmts"}
PMD_UNUSED = {"UnusedPrivateField", "UnusedLocalVariable", "UnusedPrivateMethod", "UnusedFormalParameter", "UnusedAssignment"}


@dataclass(frozen=True)
class Finding:
    category: str
    tool: str
    rule: str
    path: str
    line: int
    message: str


@dataclass(frozen=True)
class Tool:
    name: str
    stack: str
    argv: Callable[[str, Path, Path], list[str]]
    parse: Callable[[str, Path, Path], list[Finding]]
    applies: Callable[[Path], bool] = lambda root: True
    hint: str = ""
    ok: tuple[int, ...] = (0,)
    reason: str = ""
    binary: str = ""
    findings_exit: tuple[int, ...] = ()
    recover: Callable[[str, Path, dict, int], tuple[list[Finding], str | None]] | None = None
    env: Callable[[Path, Path], dict] | None = None
    fallback: Callable[[str, Path, Path], list[str]] | None = None
    fallback_note: str = ""
    stderr: bool = False
    inline: Callable[[Path], list[Finding]] | None = None


class Partial(ValueError):
    def __init__(self, message: str, findings: list[Finding]):
        super().__init__(message)
        self.findings = findings


@dataclass(frozen=True)
class Report:
    findings: list[Finding]
    skipped: list[tuple[str, str]]
    errors: list[tuple[str, str]]
    ran: list[str] = field(default_factory=list)
    dropped: int = 0


CLIPPY_GROUPS = ("correctness", "suspicious", "perf", "style", "complexity")
CLIPPY_EXTRA = ("cognitive_complexity", "too_many_arguments", "too_many_lines", "undocumented_unsafe_blocks", "missing_safety_doc", "not_unsafe_ptr_arg_deref", "multiple_unsafe_ops_per_block", "transmute_undefined_repr")
CLIPPY_IN_TESTS = ("unwrap", "expect", "panic", "indexing-slicing", "dbg")
TEST_DIRS = {"tests", "benches"}
CARGO, GO_MOD = ("Cargo.toml",), ("go.mod",)
JAVA_MARKERS = ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")


def _subdirs(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith("."))


def marker_dir(root: Path, names: tuple[str, ...]) -> Path | None:
    return next((base for base in (root, *_subdirs(root)) if any((base / n).is_file() for n in names)), None)


def detect(root: Path) -> set[str]:
    stacks = set()
    if any(root.glob("*.sln")) or any(root.glob("*.slnx")) or any(root.glob("*.csproj")) or any(root.glob("*/*.csproj")):
        stacks.add("dotnet")
    if (root / "package.json").is_file():
        stacks.add("node")
    markers = ("pyproject.toml", "setup.py", "setup.cfg")
    if any((root / m).is_file() for m in markers) or any(root.glob("requirements*.txt")) or any(root.glob("*.py")) or any(any(d.glob("*.py")) for d in _subdirs(root)):
        stacks.add("python")
    for stack, names in (("rust", CARGO), ("java", JAVA_MARKERS), ("go", GO_MOD)):
        if marker_dir(root, names):
            stacks.add(stack)
    return stacks


def resolve(name: str, root: Path, stack: str, path: str | None = None) -> str | None:
    if stack == "node":
        local = shutil.which(name, path=str(root / "node_modules" / ".bin"))
        if local:
            return local
    return shutil.which(name, path=path)


def rel(path: str, root: Path) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return Path(path).as_posix()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([shutil.which("git") or "git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def source_files(root: Path) -> list[str]:
    try:
        r = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    except OSError:
        r = None
    if r is not None and r.returncode == 0:
        names = [n for n in r.stdout.split("\0") if n]
    else:
        names = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            names += [Path(dirpath, f).relative_to(root).as_posix() for f in filenames]
    return sorted(n for n in names if SKIP_DIRS.isdisjoint(n.split("/")[:-1]) and (root / n).is_file())


def changed(root: Path, base: str) -> set[str]:
    mb = _git(root, "merge-base", base, "HEAD")
    if mb.returncode != 0:
        raise ValueError(f"{base}: {(mb.stderr.strip().splitlines() or ['not a commit'])[0]}")
    diff = _git(root, "diff", "--name-only", "--no-renames", "--relative", "-z", mb.stdout.strip())
    extra = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    for r in (diff, extra):
        if r.returncode != 0:
            raise ValueError(f"git cannot list the changed files: {_first(r.stderr) or f'exit {r.returncode}'}")
    return {n for n in (diff.stdout + "\0" + extra.stdout).split("\0") if n}


def _json(out: str, kind: type):
    data = json.loads(out)
    if not isinstance(data, kind):
        raise ValueError(f"expected a JSON {kind.__name__}")
    return data


def _lizard_files(root: Path) -> list[str]:
    return [n for n in source_files(root) if Path(n).suffix.lower() in CODE_SUFFIXES]


def _lizard_argv(exe: str, listing: Path, *extensions: str) -> list[str]:
    return [exe, *extensions, "--csv", "-f", str(listing)]


def _lizard_args(exe: str, root: Path, tmp: Path) -> list[str]:
    listing = tmp / "files.txt"
    listing.write_text("\n".join(_lizard_files(root)) + "\n", encoding="utf-8")
    return _lizard_argv(exe, listing, "-Ecognitive", "-Eduplicate")


def _lizard_crashes(exe: str, root: Path, env: dict, files: list[str], timeout: int) -> bool:
    with tempfile.TemporaryDirectory() as d:
        listing = Path(d) / "files.txt"
        listing.write_text("\n".join(files) + "\n", encoding="utf-8")
        try:
            code, _, err = _execute(_lizard_argv(exe, listing), root, env, timeout)
        except (subprocess.TimeoutExpired, OSError):
            return False
    return code != 0 and "Traceback" in err


def _split(files: list[str], ways: int) -> list[list[str]]:
    size = -(-len(files) // ways)
    return [files[i:i + size] for i in range(0, len(files), size)]


def _lizard_bad_files(exe: str, root: Path, env: dict, files: list[str], timeout: int, ways: int = 8) -> list[str]:
    bad, pending = [], _split(files, ways)
    while pending:
        with ThreadPoolExecutor(ways) as pool:
            crashed = list(pool.map(lambda chunk: _lizard_crashes(exe, root, env, chunk, timeout), pending))
        hits = [chunk for chunk, hit in zip(pending, crashed) if hit]
        bad += [chunk[0] for chunk in hits if len(chunk) == 1]
        pending = [part for chunk in hits if len(chunk) > 1 for part in _split(chunk, ways)]
    return sorted(bad)


def _lizard_recover(exe: str, root: Path, env: dict, timeout: int) -> tuple[list[Finding], str | None]:
    files = _lizard_files(root)
    bad = _lizard_bad_files(exe, root, env, files, timeout)
    if not bad:
        return [], "crashed, and no single file reproduces it"
    left = set(bad)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        listing = tmp / "files.txt"
        listing.write_text("\n".join(f for f in files if f not in left) + "\n", encoding="utf-8")
        try:
            _, out, _ = _execute(_lizard_argv(exe, listing, "-Ecognitive", "-Eduplicate"), root, env, timeout)
            found = parse_lizard(out, root, tmp)
        except (subprocess.TimeoutExpired, OSError, ValueError, IndexError) as e:
            return [], f"left out {len(bad)} files it crashes on, then failed: {e}"
    return found, f"crashes on {len(bad)} files, left out: {', '.join(bad[:3])}{' ...' if len(bad) > 3 else ''}"


def _lizard_metrics(rows: list[str], root: Path) -> list[Finding]:
    found = []
    for row in csv.reader(rows):
        if len(row) < 11 or not row[0].isdigit():
            continue
        cog = int(row[11]) if len(row) > 11 and row[11].isdigit() else 0
        path, name, start = rel(row[6], root), row[7], int(row[9])
        for rule, value, limit, label in (("cognitive-complexity", cog, COGNITIVE, "cognitive complexity"),
                                          ("cyclomatic-complexity", int(row[1]), CYCLOMATIC, "cyclomatic complexity"),
                                          ("function-length", int(row[0]), NLOC, "lines of code"),
                                          ("parameters", int(row[3]), PARAMS, "parameters")):
            if value > limit:
                found.append(Finding("complexity", "lizard", rule, path, start, f"{name} has {value} {label} (limit {limit})"))
    return found


def _lizard_duplicates(lines: list[str], root: Path) -> list[Finding]:
    found = []
    block: list[tuple[str, int, int]] = []
    for line in lines:
        m = DUP_LOC.match(line.strip())
        if m:
            block.append((rel(m.group(1), root), int(m.group(2)), int(m.group(3))))
        elif line.startswith("^^^") and block:
            (path, start, _), others = block[0], block[1:]
            where = ", ".join(f"{p}:{s}-{e}" for p, s, e in others)
            found.append(Finding("duplication", "lizard", "duplicate-block", path, start, f"same code as {where}"))
            block = []
    return found


def parse_lizard(out: str, root: Path, tmp: Path) -> list[Finding]:
    lines = out.splitlines()
    split = lines.index("Duplicates") if "Duplicates" in lines else len(lines)
    return _lizard_metrics(lines[:split], root) + _lizard_duplicates(lines[split:], root)


def parse_ruff(out: str, root: Path, tmp: Path) -> list[Finding]:
    found = []
    for item in _json(out, list):
        code = item.get("code")
        if not code:
            category, rule = "bug", "syntax"
        elif re.fullmatch(r"S\d+", code):
            category, rule = "security", code
        elif code.startswith(("C90", "PLR09")):
            category, rule = "complexity", code
        else:
            category, rule = "bug", code
        found.append(Finding(category, "ruff", rule, rel(item["filename"], root), int(item["location"]["row"]), item["message"]))
    return found


def parse_mypy(out: str, root: Path, tmp: Path) -> list[Finding]:
    return [Finding("type", "mypy", m.group(4) or "error", rel(m.group(1), root), int(m.group(2)), m.group(3))
            for m in map(MYPY.match, out.splitlines()) if m]


def parse_eslint(out: str, root: Path, tmp: Path) -> list[Finding]:
    found = []
    for result in _json(out, list):
        path = rel(result["filePath"], root)
        for msg in result.get("messages") or []:
            rule = msg.get("ruleId") or "parse"
            if rule in ESLINT_COMPLEXITY:
                category = "complexity"
            elif rule.startswith("security/") or rule in ESLINT_SECURITY:
                category = "security"
            else:
                category = "bug"
            found.append(Finding(category, "eslint", rule, path, int(msg.get("line") or 0), msg.get("message", "")))
    return found


def parse_tsc(out: str, root: Path, tmp: Path) -> list[Finding]:
    return [Finding("type", "tsc", m.group(4), rel(m.group(1), root), int(m.group(2)), m.group(5))
            for m in map(MSBUILD.match, out.splitlines()) if m]


def _dotnet_category(rule: str) -> str:
    if re.fullmatch(r"NU190[1-4]", rule):
        return "dependency"
    if rule in DOTNET_COMPLEXITY:
        return "complexity"
    if rule in DOTNET_SECURITY or rule.startswith(("CA3", "CA5", "CA23")):
        return "security"
    if rule.startswith("CS"):
        return "type"
    return "bug"


def _dotnet_lines(out: str):
    for line in (ln.strip() for ln in out.splitlines()):
        m = MSBUILD.match(line)
        if m:
            yield m.group(4), m.group(1), int(m.group(2)), m.group(5)
            continue
        m = MSBUILD_PROJECT.match(line)
        if m:
            yield m.group(3), m.group(1), 0, m.group(4)


def parse_dotnet(out: str, root: Path, tmp: Path) -> list[Finding]:
    seen: dict[tuple, Finding] = {}
    for rule, path, line, message in _dotnet_lines(out):
        f = Finding(_dotnet_category(rule), "dotnet", rule, rel(path, root), line, message)
        seen.setdefault((f.path, f.line, f.rule, f.message), f)
    return list(seen.values())


def _clippy_category(code: str, level: str) -> str:
    if code in CLIPPY_COMPLEXITY:
        return "complexity"
    if code in CLIPPY_UNSAFE:
        return "security"
    if code.startswith("unused") or code == "dead_code":
        return "unused"
    if level == "error" and not code.startswith("clippy::"):
        return "type"
    return "bug"


def _cargo_manifest(root: Path) -> Path:
    return (marker_dir(root, CARGO) or root) / "Cargo.toml"


def _cargo_data(manifest: Path) -> dict:
    try:
        return tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _jig_meta(data: dict) -> dict:
    meta = (data.get("package") or {}).get("metadata") or (data.get("workspace") or {}).get("metadata") or {}
    return meta.get("code-jig") or {}


def _own_lints(data: dict) -> bool:
    return bool(data.get("lints") or (data.get("workspace") or {}).get("lints"))


def _clippy_flags(manifest: Path, strict: bool) -> list[str]:
    data = _cargo_data(manifest)
    if _own_lints(data):
        return []
    names = [f"clippy::{n}" for n in (*CLIPPY_GROUPS, *CLIPPY_EXTRA)] + sorted(CLIPPY_PANIC - {"clippy::arithmetic_side_effects"})
    if strict or _jig_meta(data).get("strict") is True:
        names.append("clippy::arithmetic_side_effects")
    return [a for n in names for a in ("-W", n)]


def _clippy_env(root: Path, tmp: Path) -> dict:
    manifest = _cargo_manifest(root)
    if (manifest.parent / "clippy.toml").is_file() or (manifest.parent / ".clippy.toml").is_file() or _own_lints(_cargo_data(manifest)):
        return {}
    (tmp / "clippy.toml").write_text("".join(f"allow-{n}-in-tests = true\n" for n in CLIPPY_IN_TESTS), encoding="utf-8")
    return {"CLIPPY_CONF_DIR": str(tmp)}


def _host_triple() -> str | None:
    rustc = shutil.which("rustc")
    if rustc is None:
        return None
    try:
        out = subprocess.run([rustc, "-vV"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False).stdout
    except OSError:
        return None
    return next((ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.startswith("host:")), None)


def _config_sets_target(start: Path) -> bool:
    for base in (start, *start.parents):
        for name in ("config.toml", "config"):
            f = base / ".cargo" / name
            if f.is_file() and (_cargo_data(f).get("build") or {}).get("target"):
                return True
    return False


def _clippy_target(manifest: Path, data: dict) -> list[str]:
    target = _jig_meta(data).get("target")
    if not isinstance(target, str):
        target = _host_triple() if _config_sets_target(manifest.parent) else None
    return ["--target", target] if target else []


def _clippy_argv(exe: str, root: Path, strict: bool, all_features: bool = True) -> list[str]:
    manifest = _cargo_manifest(root)
    data = _cargo_data(manifest)
    scope = ["--workspace"] if "workspace" in data else []
    features = ["--all-features"] if all_features and data.get("features") else []
    return [exe, "clippy", "--manifest-path", str(manifest), "--offline", "--all-targets", *scope, *features, *_clippy_target(manifest, data),
            "--message-format", "json", "--quiet", "--", *_clippy_flags(manifest, strict)]


def clippy_tool(strict: bool = False) -> Tool:
    return Tool("clippy", "rust", lambda exe, root, tmp: _clippy_argv(exe, root, strict), parse_clippy, hint="rustup component add clippy",
                binary="cargo", findings_exit=(101,), env=_clippy_env, fallback=lambda exe, root, tmp: _clippy_argv(exe, root, strict, False),
                fallback_note="--all-features does not compile (conflicting features?); analyzed the default features only")


def parse_clippy(out: str, root: Path, tmp: Path) -> list[Finding]:
    found = []
    for line in out.splitlines():
        if not line.startswith("{"):
            continue
        data = json.loads(line)
        msg = data.get("message") if data.get("reason") == "compiler-message" else None
        span = next((s for s in (msg or {}).get("spans") or [] if s.get("is_primary")), None)
        if span is None or msg.get("level") not in ("warning", "error"):
            continue
        code = (msg.get("code") or {}).get("code") or ""
        path = rel(str(_cargo_manifest(root).parent / span["file_name"]), root)
        if code in CLIPPY_PANIC and not TEST_DIRS.isdisjoint(Path(path).parts[:-1]):
            continue
        found.append(Finding(_clippy_category(code, msg["level"]), "clippy", code or msg["level"], path, int(span["line_start"]), msg["message"]))
    return found


def _cargo_home() -> Path:
    return Path(os.environ.get("CARGO_HOME") or Path.home() / ".cargo")


def _audit_ready(root: Path) -> bool:
    return (_cargo_manifest(root).parent / "Cargo.lock").is_file() and (_cargo_home() / "advisory-db").is_dir()


def parse_cargo_audit(out: str, root: Path, tmp: Path) -> list[Finding]:
    report = _json(out, dict)
    items = list((report.get("vulnerabilities") or {}).get("list") or [])
    for group in (report.get("warnings") or {}).values():
        items += group if isinstance(group, list) else []
    lock = rel(str(_cargo_manifest(root).parent / "Cargo.lock"), root)
    return [Finding("dependency", "cargo-audit", (i.get("advisory") or {}).get("id") or i.get("kind", "advisory"), lock, 0,
                    f"{(i.get('package') or {}).get('name', '?')}@{(i.get('package') or {}).get('version', '?')}: "
                    f"{(i.get('advisory') or {}).get('title') or i.get('kind', '')}")
            for i in items]


def _toml_line(path: Path, name: str) -> int:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*[=.]|^\s*\[(?:\w+[-.])*{re.escape(name)}\]")
    return next((n for n, ln in enumerate(lines, 1) if pattern.match(ln)), 0)


def parse_cargo_machete(out: str, root: Path, tmp: Path) -> list[Finding]:
    found, manifest = [], None
    for line in out.splitlines():
        if line.endswith(":") and " -- " in line:
            manifest = Path(line.rsplit(" -- ", 1)[1][:-1])
            manifest = manifest if manifest.is_absolute() else root / manifest
        elif manifest is not None and line[:1] in ("\t", " ") and line.strip():
            name = line.strip()
            found.append(Finding("unused", "cargo-machete", "unused-dependency", rel(str(manifest), root), _toml_line(manifest, name),
                                 f"dependency {name} is declared but never used"))
    return found


def parse_cargo_deny(out: str, root: Path, tmp: Path) -> list[Finding]:
    found = []
    for line in out.splitlines():
        if not line.startswith("{"):
            continue
        entry = json.loads(line)
        fields = entry.get("fields") or {}
        if entry.get("type") == "diagnostic" and fields.get("severity") in ("error", "warning"):
            found.append(Finding("dependency", "cargo-deny", fields.get("code") or "diagnostic", "Cargo.lock", 0, fields.get("message", "")))
    return found


def scan_unsafe(root: Path) -> list[Finding]:
    found = []
    for name in source_files(root):
        if not name.endswith(".rs"):
            continue
        try:
            total, bare = unsafe_scan.undocumented((root / name).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        found += [Finding("security", "unsafe-scan", "undocumented-unsafe", name, n,
                          f"low: unsafe without a SAFETY comment ({total} unsafe in this file)") for n in bare]
    return found


def parse_go_vet(out: str, root: Path, tmp: Path) -> list[Finding]:
    found, decoder, pos = [], json.JSONDecoder(), 0
    while pos < len(out) and out[pos:].strip():
        pos += len(out[pos:]) - len(out[pos:].lstrip())
        package, pos = decoder.raw_decode(out, pos)
        for analyzers in package.values():
            for rule, items in analyzers.items():
                for item in items if isinstance(items, list) else []:
                    path, line = GO_POSN.match(item["posn"]).groups()
                    found.append(Finding("bug", "go-vet", rule, rel(path, root), int(line), item["message"]))
    return found


def _pmd_category(violation: dict) -> str:
    rule = violation["rule"]
    if rule in PMD_COMPLEXITY:
        return "complexity"
    if rule in PMD_UNUSED:
        return "unused"
    return "security" if violation.get("ruleset") == "Security" else "bug"


def parse_pmd(out: str, root: Path, tmp: Path) -> list[Finding]:
    return [Finding(_pmd_category(v), "pmd", v["rule"], rel(f["filename"], root), int(v["beginline"]), v["description"])
            for f in _json(out, dict).get("files") or [] for v in f.get("violations") or []]


def parse_vulture(out: str, root: Path, tmp: Path) -> list[Finding]:
    found = []
    for m in map(VULTURE.match, out.splitlines()):
        if m:
            rule = re.sub(r"\W+", "-", re.sub(r"'[^']*'", " ", m.group(3)).strip().lower()).strip("-")
            found.append(Finding("unused", "vulture", rule, rel(m.group(1), root), int(m.group(2)), f"{m.group(3)} ({m.group(4)}% confidence)"))
    return found


def _knip_item(entry: dict, key: str, item, root: Path) -> Finding:
    category = "bug" if key in KNIP_BROKEN else "unused"
    if isinstance(item, list):
        names = " -> ".join(str(i.get("name", "")) for i in item)
        return Finding(category, "knip", f"knip/{key}", rel(entry["file"], root), 0, f"{key}: {names}")
    name = ".".join(str(part) for part in (item.get("namespace"), item.get("name", "")) if part)
    return Finding(category, "knip", f"knip/{key}", rel(entry["file"], root), int(item.get("line") or 0), f"{key}: {name}")


def parse_knip(out: str, root: Path, tmp: Path) -> list[Finding]:
    issues = _json(out, dict).get("issues")
    if not isinstance(issues, list):
        raise ValueError("expected an issues list")
    return [_knip_item(entry, key, item, root)
            for entry in issues for key in KNIP_UNUSED + KNIP_BROKEN for item in entry.get(key) or []]


def parse_semgrep(out: str, root: Path, tmp: Path) -> list[Finding]:
    data = _json(out, dict)
    found = [Finding("security", "semgrep", r["check_id"], rel(r["path"], root), int(r["start"]["line"]), r["extra"].get("message", ""))
             for r in data.get("results") or []]
    errors = data.get("errors") or []
    if errors:
        first = errors[0] if isinstance(errors[0], dict) else {"message": str(errors[0])}
        raise Partial(f"{len(errors)} errors, first: {first.get('type', 'error')}: {first.get('message', '')}".strip(), found)
    return found


def parse_gitleaks(out: str, root: Path, tmp: Path) -> list[Finding]:
    report = tmp / "gitleaks.json"
    if not report.is_file() or not report.read_text(encoding="utf-8").strip():
        return []
    return [Finding("secret", "gitleaks", r.get("RuleID", "secret"), rel(r["File"], root), int(r.get("StartLine") or 0),
                    r.get("Description", "") + (f" (fingerprint {r['Fingerprint']})" if r.get("Fingerprint") else ""))
            for r in _json(report.read_text(encoding="utf-8"), list)]


def parse_osv(out: str, root: Path, tmp: Path) -> list[Finding]:
    if not out.strip():
        return []
    found = []
    for result in _json(out, dict).get("results") or []:
        path = rel(result["source"]["path"], root)
        for pkg in result.get("packages") or []:
            name = f"{pkg['package']['name']}@{pkg['package'].get('version', '?')}"
            for vuln in pkg.get("vulnerabilities") or []:
                found.append(Finding("dependency", "osv-scanner", vuln["id"], path, 0, f"{name}: {vuln.get('summary', '')}"))
    return found


def _has_mypy_config(root: Path) -> bool:
    def contains(name: str, text: str) -> bool:
        f = root / name
        return f.is_file() and text in f.read_text(encoding="utf-8", errors="replace")
    return (root / "mypy.ini").is_file() or (root / ".mypy.ini").is_file() or contains("setup.cfg", "[mypy") or contains("pyproject.toml", "[tool.mypy")


def _vulture_args(exe: str, root: Path, tmp: Path) -> list[str]:
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and "[tool.vulture" in pyproject.read_text(encoding="utf-8", errors="replace"):
        return [exe]
    excludes = ",".join(f"{d}/*,*/{d}/*" for d in sorted(SKIP_DIRS))
    return [exe, ".", "--min-confidence", "80", "--exclude", excludes]


def _has_eslint_config(root: Path) -> bool:
    return any(root.glob("eslint.config.*")) or any(root.glob(".eslintrc*"))


def _semgrep_rules(root: Path) -> Path | None:
    for name in (".semgrep.yml", ".semgrep.yaml", ".semgrep"):
        if (root / name).exists():
            return root / name
    return None


def _dotnet_target(root: Path) -> list[str]:
    for pattern in ("*.sln", "*.slnx", "*.csproj"):
        found = sorted(root.glob(pattern))
        if found:
            return [found[0].name]
    return []


_GITLEAKS = ("--no-banner", "--redact", "--exit-code", "0", "--report-format", "json", "--report-path")
RE2_SPECIAL = re.compile(r"([.^$*+?()\[\]{}|\\])")


def _ignored_paths(root: Path, limit: int = 500) -> list[str]:
    r = _git(root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory")
    names = [n for n in r.stdout.split("\0") if n] if r.returncode == 0 else []
    return names if len(names) <= limit else []


def _gitleaks_config(ignored: list[str]) -> str:
    alternatives = "|".join(RE2_SPECIAL.sub(r"\\\1", n.rstrip("/")) + ("/" if n.endswith("/") else "$") for n in ignored)
    return f"[extend]\nuseDefault = true\n\n[[allowlists]]\npaths = ['''(^|/)({alternatives})''']\n"


def _gitleaks_dir_args(exe: str, root: Path, tmp: Path) -> list[str]:
    args = [exe, "dir", *_GITLEAKS, str(tmp / "gitleaks.json")]
    ignored = _ignored_paths(root)
    if ignored:
        (tmp / "gitleaks.toml").write_text(_gitleaks_config(ignored), encoding="utf-8")
        args += ["--config", str(tmp / "gitleaks.toml")]
    return [*args, "."]


SCANNERS = ("gitleaks", "gitleaks-history", "osv-scanner", "semgrep")

_RUFF_TEST_ASSERTS = tuple(a for g in ("tests/**", "test/**", "**/tests/**", "**/test_*.py", "**/*_test.py", "**/conftest.py")
                          for a in ("--extend-per-file-ignores", f"{g}:S101"))

TOOLS = [
    Tool("lizard", "any", _lizard_args, parse_lizard, hint="pip install lizard", recover=_lizard_recover),
    Tool("ruff", "python", lambda exe, root, tmp: [exe, "check", "--output-format", "json", "--no-cache", "--exit-zero", "--extend-select", "S,B", *_RUFF_TEST_ASSERTS, "."],
         parse_ruff, hint="pip install ruff"),
    Tool("vulture", "python", _vulture_args,
         parse_vulture, hint="pip install vulture", ok=(0, 3)),
    Tool("mypy", "python", lambda exe, root, tmp: [exe, "--no-error-summary", "--no-pretty", "--show-error-codes", "."],
         parse_mypy, _has_mypy_config, "pip install mypy", reason="no mypy config", findings_exit=(1,)),
    Tool("eslint", "node", lambda exe, root, tmp: [exe, ".", "-f", "json"], parse_eslint, _has_eslint_config,
         "npm install -D eslint eslint-plugin-sonarjs", reason="no eslint config", findings_exit=(1,)),
    Tool("knip", "node", lambda exe, root, tmp: [exe, "--reporter", "json", "--no-progress"], parse_knip,
         hint="npm install -D knip", findings_exit=(1,)),
    Tool("tsc", "node", lambda exe, root, tmp: [exe, "--noEmit", "--pretty", "false", "-p", "."], parse_tsc,
         lambda root: (root / "tsconfig.json").is_file(), "npm install -D typescript", reason="no tsconfig.json", findings_exit=(1, 2)),
    Tool("dotnet", "dotnet", lambda exe, root, tmp: [exe, "build", "--nologo", "--no-incremental", "-clp:NoSummary", *_dotnet_target(root)],
         parse_dotnet, lambda root: bool(_dotnet_target(root)), "install the .NET SDK", reason="no solution or project at the root", findings_exit=(1,)),
    clippy_tool(),
    Tool("cargo-audit", "rust", lambda exe, root, tmp: [exe, "audit", "--json", "--no-fetch", "--file", str(_cargo_manifest(root).parent / "Cargo.lock")],
         parse_cargo_audit, _audit_ready, "cargo install cargo-audit, then run it once online to fetch the advisory db",
         reason="no Cargo.lock, or no advisory db in ~/.cargo/advisory-db (run cargo audit once online)", binary="cargo-audit", findings_exit=(1,)),
    Tool("cargo-machete", "rust", lambda exe, root, tmp: [exe, str(_cargo_manifest(root).parent)], parse_cargo_machete,
         hint="cargo install cargo-machete", binary="cargo-machete", findings_exit=(1,)),
    Tool("cargo-deny", "rust", lambda exe, root, tmp: [exe, "--manifest-path", str(_cargo_manifest(root)), "--format", "json", "check", "--disable-fetch"],
         parse_cargo_deny, lambda root: (_cargo_manifest(root).parent / "deny.toml").is_file(), "cargo install cargo-deny", reason="no deny.toml",
         binary="cargo-deny", findings_exit=(1,), stderr=True),
    Tool("unsafe-scan", "rust", lambda exe, root, tmp: [], lambda out, root, tmp: [], inline=scan_unsafe),
    Tool("pmd", "java", lambda exe, root, tmp: [exe, "check", "-d", ".", "-R", "rulesets/java/quickstart.xml", "-f", "json", "--no-cache", "--no-progress"],
         parse_pmd, hint="install PMD 7 from its GitHub releases", findings_exit=(4,)),
    Tool("go-vet", "go", lambda exe, root, tmp: [exe, "-C", str(marker_dir(root, GO_MOD) or root), "vet", "-json", "./..."], parse_go_vet, hint="install Go", binary="go"),
    Tool("semgrep", "any", lambda exe, root, tmp: [exe, "scan", "--metrics=off", "--disable-version-check", "--config", str(_semgrep_rules(root)), "--json", "--quiet", "."],
         parse_semgrep, lambda root: _semgrep_rules(root) is not None, "pip install semgrep", reason="no local rules (.semgrep.yml or .semgrep/)"),
    Tool("gitleaks", "any", _gitleaks_dir_args,
         parse_gitleaks, hint="install gitleaks from its GitHub releases", binary="gitleaks"),
    Tool("gitleaks-history", "any", lambda exe, root, tmp: [exe, "git", *_GITLEAKS, str(tmp / "gitleaks.json"), "."],
         parse_gitleaks, lambda root: (root / ".git").exists(), "install gitleaks from its GitHub releases", reason="not a git repository", binary="gitleaks"),
    Tool("osv-scanner", "any", lambda exe, root, tmp: [exe, "scan", "source", "-r", "--offline", "--download-offline-databases", "--format", "json", "."],
         parse_osv, hint="install osv-scanner from its GitHub releases", ok=(0, 1, 128)),
]


PROGRESS = ("#", "go: downloading", "go: finding", "go: extracting")


def _first(text: str) -> str:
    return next((ln for ln in text.strip().splitlines() if ln.strip() and not ln.startswith(PROGRESS)), "")[:300]


def _kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        proc.kill()


def _execute(argv: list[str], root: Path, env: dict, timeout: int) -> tuple[int, str, str]:
    group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding="utf-8", errors="replace", **group) as proc:
        try:
            out, err = proc.communicate(timeout=timeout)
        except BaseException:
            _kill_tree(proc)
            proc.communicate()
            raise
    return proc.returncode, out, err


def _launch(t: Tool, argv: list[str], root: Path, env: dict, tmp: Path, timeout: int) -> tuple[int, str, str]:
    return _execute(argv, root, {**env, **(t.env(root, tmp) if t.env else {})}, timeout)


def _has_type_error(t: Tool, out: str, root: Path, tmp: Path) -> bool:
    try:
        return any(f.category == "type" for f in t.parse(out, root, tmp))
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, Partial):
        return False


def _run_inline(t: Tool, root: Path) -> tuple[list[Finding], str | None]:
    try:
        return t.inline(root), None
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as e:
        return [], f"failed: {e}"


def _run_one(t: Tool, exe: str, root: Path, env: dict, timeout: int) -> tuple[list[Finding], str | None]:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        error = None
        try:
            code, out, err = _launch(t, t.argv(exe, root, tmp), root, env, tmp, timeout)
            if t.fallback and code not in t.ok and _has_type_error(t, out, root, tmp):
                code, out, err = _launch(t, t.fallback(exe, root, tmp), root, env, tmp, timeout)
                error = None if _has_type_error(t, out, root, tmp) else t.fallback_note
        except subprocess.TimeoutExpired:
            return [], f"timed out after {timeout}s"
        except OSError as e:
            return [], f"cannot run: {e}"
        out = err if t.stderr else out
        if code not in t.ok and t.recover and "Traceback" in err:
            return t.recover(exe, root, env, timeout)
        try:
            found = t.parse(out, root, tmp)
        except Partial as e:
            found, error = e.findings, str(e)
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as e:
            return [], f"unreadable output: {e}; {_first(err)}"
    if code not in t.ok and (code not in t.findings_exit or not found):
        error = f"exit {code}: {_first(err) or _first(out)}"
    return found, error


def _own_code(path: str) -> bool:
    return not (path.startswith("/") or PureWindowsPath(path).is_absolute()) and SKIP_DIRS.isdisjoint(Path(path).parts[:-1])


def _wanted(tool: str, f: Finding, root: Path) -> bool:
    if tool in ("gitleaks", "osv-scanner"):
        return _git(root, "check-ignore", "-q", "--", f.path).returncode != 0
    return tool in SCANNERS or _own_code(f.path)


def _add_new(findings: list[Finding], seen: set, found: list[Finding]) -> None:
    for f in found:
        key = (f.tool, f.rule, f.path, f.line, "" if f.line else f.message)
        if key not in seen:
            seen.add(key)
            findings.append(f)


def run_tools(tools: list[Tool], root: Path, stacks: set[str], path: str | None = None, timeout: int = 600) -> Report:
    report = Report([], [], [])
    env = {**os.environ, **TOOL_ENV}
    if path is not None:
        env["PATH"] = path
    seen = set()
    for t in tools:
        if not stacks or (t.stack != "any" and t.stack not in stacks):
            continue
        if not t.applies(root):
            report.skipped.append((t.name, t.reason))
            continue
        exe = resolve(t.binary or t.name, root, t.stack, path) if t.inline is None else sys.executable
        if exe is None:
            report.skipped.append((t.name, f"not installed; {t.hint}"))
            continue
        found, error = _run_inline(t, root) if t.inline else _run_one(t, exe, root, env, timeout)
        if t.inline:
            covered = {(f.path, f.line) for f in report.findings if f.rule == "clippy::undocumented_unsafe_blocks"}
            found = [f for f in found if (f.path, f.line) not in covered]
        report.ran.append(t.name)
        kept = [f for f in found if _wanted(t.name, f, root)]
        report = replace(report, dropped=report.dropped + len(found) - len(kept))
        _add_new(report.findings, seen, kept)
        if error:
            report.errors.append((t.name, error))
    return report


def printable(text: str) -> str:
    return "".join(ch if ch.isprintable() else f"\\x{ord(ch):02x}" for ch in text)


def render(report: Report, stacks: set[str], top: int = 10) -> list[str]:
    counts = Counter(f.category for f in report.findings)
    out = [f"analyze: {', '.join(sorted(stacks))}", "  ".join(f"{c} {counts.get(c, 0)}" for c in CATEGORIES)]
    for category in CATEGORIES:
        items = sorted((f for f in report.findings if f.category == category), key=lambda f: (f.path, f.line, f.rule))
        if not items:
            continue
        out.append(f"== {category} ({len(items)})")
        for f in items[:top]:
            where = f"{f.path}:{f.line}" if f.line else f.path
            out.append(f"  {printable(where)}  {printable(f.rule)}  {printable(f.message)[:200]}")
        if len(items) > top:
            out.append(f"  and {len(items) - top} more")
    if report.dropped:
        out.append(f"not shown: {report.dropped} findings in generated, vendored or external paths, or in git-ignored files")
    out += [f"skipped: {name} ({why})" for name, why in report.skipped]
    out += [f"error: {name}: {printable(why)}" for name, why in report.errors]
    return out


def utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def cli(args) -> int:
    utf8_stdout()
    root = Path(args.path).resolve()
    stacks = detect(root)
    if not stacks:
        print(f"code-jig: no .NET, Node, Python, Rust, Java or Go project found in {root}", file=sys.stderr)
        return 2
    try:
        keep = changed(root, args.base) if args.base else None
    except (ValueError, OSError) as e:
        print(f"code-jig: {e}", file=sys.stderr)
        return 2
    tools = [clippy_tool(True) if t.name == "clippy" and getattr(args, "strict", False) else t for t in TOOLS]
    report = run_tools(tools, root, stacks, timeout=args.timeout)
    if keep is not None:
        report = Report([f for f in report.findings if f.path in keep], report.skipped, report.errors, report.ran, report.dropped)
    if args.json:
        print(json.dumps({"stacks": sorted(stacks), "findings": [asdict(f) for f in report.findings],
                          "skipped": report.skipped, "errors": report.errors, "dropped": report.dropped}, ensure_ascii=False, indent=1))
    else:
        for line in render(report, stacks, args.top):
            print(line)
    if not report.ran:
        print("code-jig: no analyzer ran; install at least one of the skipped tools", file=sys.stderr)
        return 2
    return 1 if report.findings or report.errors else 0
