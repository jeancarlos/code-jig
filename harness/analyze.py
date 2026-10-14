from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

CATEGORIES = ("security", "secret", "dependency", "bug", "type", "complexity", "duplication")
OPT_OUT = {"SEMGREP_SEND_METRICS": "off", "SEMGREP_ENABLE_VERSION_CHECK": "0", "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
           "DOTNET_NOLOGO": "1", "KIOTA_CLI_TELEMETRY_OPTOUT": "1"}
COGNITIVE, CYCLOMATIC, NLOC, PARAMS = 15, 15, 100, 7
SKIP_DIRS = {".git", "node_modules", "bin", "obj", ".venv", "venv", "dist", "build", "__pycache__"}
ESLINT_COMPLEXITY = {"complexity", "max-depth", "max-lines-per-function", "max-params", "max-nested-callbacks",
                     "sonarjs/cognitive-complexity", "sonarjs/cyclomatic-complexity", "sonarjs/nested-control-flow"}
ESLINT_SECURITY = {"sonarjs/os-command", "sonarjs/sql-queries", "sonarjs/code-eval", "sonarjs/pseudo-random",
                   "sonarjs/no-hardcoded-passwords", "sonarjs/no-hardcoded-ip", "sonarjs/hashing", "sonarjs/insecure-cookie",
                   "sonarjs/weak-ssl", "sonarjs/no-clear-text-protocols"}
DOTNET_COMPLEXITY = {"S3776", "S1541", "S138", "S107", "CA1502", "CA1505", "CA1506"}
DOTNET_SECURITY = {"CA2100", "S2068", "S2077", "S2245", "S3649", "S4423", "S4426", "S4433", "S4507", "S4790",
                   "S5332", "S5344", "S5443", "S5542", "S5547", "S5659", "S5773", "S6418"}
MSBUILD = re.compile(r"^(.+?)\((\d+),\d+\): (warning|error) ([A-Za-z]+\d+): (.*?)(?: \[[^\]]*\])?$")
MYPY = re.compile(r"^(.+?):(\d+): error: (.*?)(?:  \[([\w-]+)\])?$")
DUP_LOC = re.compile(r"^(.+):(\d+) ~ (\d+)$")


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
    ok: tuple[int, ...] = (0, 1)
    reason: str = ""


@dataclass(frozen=True)
class Report:
    findings: list[Finding]
    skipped: list[tuple[str, str]]
    errors: list[tuple[str, str]]


def detect(root: Path) -> set[str]:
    stacks = set()
    if any(root.glob("*.sln")) or any(root.glob("*.slnx")) or any(root.glob("*.csproj")) or any(root.glob("*/*.csproj")):
        stacks.add("dotnet")
    if (root / "package.json").is_file():
        stacks.add("node")
    markers = ("pyproject.toml", "setup.py", "setup.cfg")
    if any((root / m).is_file() for m in markers) or any(root.glob("requirements*.txt")) or any(root.glob("*.py")):
        stacks.add("python")
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
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")


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
    return sorted(n for n in names if (root / n).is_file())


def changed(root: Path, base: str) -> set[str]:
    mb = _git(root, "merge-base", base, "HEAD")
    if mb.returncode != 0:
        raise ValueError(f"{base}: {(mb.stderr.strip().splitlines() or ['not a commit'])[0]}")
    diff = _git(root, "diff", "--name-only", "--no-renames", "--relative", "-z", mb.stdout.strip())
    extra = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return {n for n in (diff.stdout + "\0" + extra.stdout).split("\0") if n}


def _json(out: str, kind: type):
    data = json.loads(out)
    if not isinstance(data, kind):
        raise ValueError(f"expected a JSON {kind.__name__}")
    return data


def _lizard_args(exe: str, root: Path, tmp: Path) -> list[str]:
    listing = tmp / "files.txt"
    listing.write_text("\n".join(source_files(root)) + "\n", encoding="utf-8")
    return [exe, "-Ecognitive", "-Eduplicate", "--csv", "-f", str(listing)]


def parse_lizard(out: str, root: Path, tmp: Path) -> list[Finding]:
    found = []
    lines = out.splitlines()
    split = lines.index("Duplicates") if "Duplicates" in lines else len(lines)
    for row in csv.reader(lines[:split]):
        if len(row) < 11 or not row[0].isdigit():
            continue
        nloc, ccn, params, path, name, start = int(row[0]), int(row[1]), int(row[3]), rel(row[6], root), row[7], int(row[9])
        cog = int(row[11]) if len(row) > 11 and row[11].isdigit() else 0
        for rule, value, limit, label in (("cognitive-complexity", cog, COGNITIVE, "cognitive complexity"),
                                          ("cyclomatic-complexity", ccn, CYCLOMATIC, "cyclomatic complexity"),
                                          ("function-length", nloc, NLOC, "lines of code"),
                                          ("parameters", params, PARAMS, "parameters")):
            if value > limit:
                found.append(Finding("complexity", "lizard", rule, path, start, f"{name} has {value} {label} (limit {limit})"))
    block: list[tuple[str, int, int]] = []
    for line in lines[split:]:
        m = DUP_LOC.match(line.strip())
        if m:
            block.append((rel(m.group(1), root), int(m.group(2)), int(m.group(3))))
        elif line.startswith("^^^") and block:
            (path, start, _), others = block[0], block[1:]
            where = ", ".join(f"{p}:{s}-{e}" for p, s, e in others)
            found.append(Finding("duplication", "lizard", "duplicate-block", path, start, f"same code as {where}"))
            block = []
    return found


def parse_ruff(out: str, root: Path, tmp: Path) -> list[Finding]:
    found = []
    for item in _json(out, list):
        code = item.get("code")
        if not code:
            category, rule = "bug", "syntax"
        elif code.startswith("S"):
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
    if rule in DOTNET_COMPLEXITY:
        return "complexity"
    if rule in DOTNET_SECURITY or rule.startswith(("CA3", "CA5", "CA23")):
        return "security"
    if rule.startswith("CS"):
        return "type"
    return "bug"


def parse_dotnet(out: str, root: Path, tmp: Path) -> list[Finding]:
    seen: dict[tuple, Finding] = {}
    for m in map(MSBUILD.match, (ln.strip() for ln in out.splitlines())):
        if m:
            f = Finding(_dotnet_category(m.group(4)), "dotnet", m.group(4), rel(m.group(1), root), int(m.group(2)), m.group(5))
            seen.setdefault((f.path, f.line, f.rule, f.message), f)
    return list(seen.values())


def parse_semgrep(out: str, root: Path, tmp: Path) -> list[Finding]:
    return [Finding("security", "semgrep", r["check_id"], rel(r["path"], root), int(r["start"]["line"]), r["extra"].get("message", ""))
            for r in _json(out, dict).get("results") or []]


def parse_gitleaks(out: str, root: Path, tmp: Path) -> list[Finding]:
    report = tmp / "gitleaks.json"
    if not report.is_file() or not report.read_text(encoding="utf-8").strip():
        return []
    return [Finding("secret", "gitleaks", r.get("RuleID", "secret"), rel(r["File"], root), int(r.get("StartLine") or 0), r.get("Description", ""))
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


TOOLS = [
    Tool("lizard", "any", _lizard_args, parse_lizard, hint="pip install lizard"),
    Tool("ruff", "python", lambda exe, root, tmp: [exe, "check", "--output-format", "json", "--no-cache", "--exit-zero", "--extend-select", "S,B", "."],
         parse_ruff, hint="pip install ruff"),
    Tool("mypy", "python", lambda exe, root, tmp: [exe, "--no-error-summary", "--no-pretty", "--show-error-codes", "."],
         parse_mypy, _has_mypy_config, "pip install mypy", reason="no mypy config"),
    Tool("eslint", "node", lambda exe, root, tmp: [exe, ".", "-f", "json"], parse_eslint, _has_eslint_config,
         "npm install -D eslint eslint-plugin-sonarjs", reason="no eslint config"),
    Tool("tsc", "node", lambda exe, root, tmp: [exe, "--noEmit", "--pretty", "false", "-p", "."], parse_tsc,
         lambda root: (root / "tsconfig.json").is_file(), "npm install -D typescript", (0, 1, 2), "no tsconfig.json"),
    Tool("dotnet", "dotnet", lambda exe, root, tmp: [exe, "build", "--nologo", "--no-incremental", "-clp:NoSummary", *_dotnet_target(root)],
         parse_dotnet, lambda root: bool(_dotnet_target(root)), "install the .NET SDK", reason="no solution or project at the root"),
    Tool("semgrep", "any", lambda exe, root, tmp: [exe, "scan", "--metrics=off", "--disable-version-check", "--config", str(_semgrep_rules(root)), "--json", "--quiet", "."],
         parse_semgrep, lambda root: _semgrep_rules(root) is not None, "pip install semgrep", reason="no local rules (.semgrep.yml or .semgrep/)"),
    Tool("gitleaks", "any", lambda exe, root, tmp: [exe, "git" if (root / ".git").exists() else "dir", "--no-banner", "--redact", "--exit-code", "0",
                                                    "--report-format", "json", "--report-path", str(tmp / "gitleaks.json"), "."],
         parse_gitleaks, hint="install gitleaks from its GitHub releases"),
    Tool("osv-scanner", "any", lambda exe, root, tmp: [exe, "scan", "source", "-r", "--offline", "--download-offline-databases", "--format", "json", "."],
         parse_osv, hint="install osv-scanner from its GitHub releases", ok=(0, 1, 128)),
]


def _first(text: str) -> str:
    return (text.strip().splitlines() or [""])[0][:300]


def run_tools(tools: list[Tool], root: Path, stacks: set[str], path: str | None = None, timeout: int = 600) -> Report:
    findings: list[Finding] = []
    skipped: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    env = {**os.environ, **OPT_OUT}
    if path is not None:
        env["PATH"] = path
    for t in tools:
        if not stacks or (t.stack != "any" and t.stack not in stacks):
            continue
        if not t.applies(root):
            skipped.append((t.name, t.reason))
            continue
        exe = resolve(t.name, root, t.stack, path)
        if exe is None:
            skipped.append((t.name, f"not installed; {t.hint}"))
            continue
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            try:
                r = subprocess.run(t.argv(exe, root, tmp), cwd=root, env=env, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout)
            except subprocess.TimeoutExpired:
                errors.append((t.name, f"timed out after {timeout}s"))
                continue
            except OSError as e:
                errors.append((t.name, f"cannot run: {e}"))
                continue
            try:
                found = t.parse(r.stdout, root, tmp)
            except (ValueError, KeyError, TypeError, IndexError, AttributeError) as e:
                errors.append((t.name, f"unreadable output: {e}; {_first(r.stderr)}"))
                continue
        if r.returncode not in t.ok and not found:
            errors.append((t.name, f"exit {r.returncode}: {_first(r.stderr) or _first(r.stdout)}"))
        findings += found
    return Report(findings, skipped, errors)


def _clean(text: str) -> str:
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
            out.append(f"  {_clean(where)}  {_clean(f.rule)}  {_clean(f.message)[:200]}")
        if len(items) > top:
            out.append(f"  and {len(items) - top} more")
    out += [f"skipped: {name} ({why})" for name, why in report.skipped]
    out += [f"error: {name}: {_clean(why)}" for name, why in report.errors]
    return out


def cli(args) -> int:
    root = Path(args.path).resolve()
    stacks = detect(root)
    if not stacks:
        print(f"harness: no .NET, Node or Python project found in {root}", file=sys.stderr)
        return 2
    try:
        keep = changed(root, args.base) if args.base else None
    except (ValueError, OSError) as e:
        print(f"harness: {e}", file=sys.stderr)
        return 2
    report = run_tools(TOOLS, root, stacks, timeout=args.timeout)
    if keep is not None:
        report = Report([f for f in report.findings if f.path in keep], report.skipped, report.errors)
    if args.json:
        print(json.dumps({"stacks": sorted(stacks), "findings": [asdict(f) for f in report.findings],
                          "skipped": report.skipped, "errors": report.errors}, ensure_ascii=False, indent=1))
    else:
        for line in render(report, stacks, args.top):
            print(line)
    return 1 if report.findings or report.errors else 0
