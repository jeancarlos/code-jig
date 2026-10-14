import os
import re
import subprocess
from pathlib import Path

from harness.install import MARKER_BODY, is_generated
from harness.tiers import Tier

Check = tuple[str, str, str]
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SUMMARY = re.compile(r"^(model|reasoning effort): (.+)$")


def command(bin_path: Path) -> list[str]:
    return [str(bin_path)]


def run_codex(bin_path: Path, home: Path, args: list[str], cwd: Path, timeout: int):
    env = dict(os.environ, CODEX_HOME=str(home))
    try:
        return subprocess.run([*command(bin_path), *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, cwd=cwd, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return f"timed out after {timeout}s"
    except OSError as e:
        return f"cannot run {bin_path}: {e.strerror or e}"


def _error(r: subprocess.CompletedProcess) -> str:
    lines = [ln for ln in r.stderr.splitlines() if ln.strip() and not ln.startswith("WARNING:")]
    return lines[0] if lines else f"exit {r.returncode}"


def _digest(home: Path) -> str:
    agents = home / "AGENTS.md"
    if not agents.is_file() or not is_generated(agents):
        return ""
    first = agents.read_bytes().removeprefix(b"\xef\xbb\xbf").split(b"\n", 1)[0].decode("utf-8", "replace")
    return first.split(MARKER_BODY, 1)[1].split(" ", 1)[0]


def check_prompt(bin_path: Path | None, home: Path, cwd: Path, ts: list[Tier]) -> list[Check]:
    if bin_path is None:
        return [("warn", "prompt probe", "codex not found; skipped")]
    digest = _digest(home)
    checks = []
    for t in ts:
        name = f"tier {t.name} prompt"
        r = run_codex(bin_path, home, ["--profile", t.name, "debug", "prompt-input", "ping"], cwd, 120)
        if isinstance(r, str):
            checks.append(("FAIL", name, r))
        elif r.returncode != 0:
            checks.append(("FAIL", name, _error(r)))
        elif digest and f"sha256:{digest}" not in r.stdout:
            checks.append(("FAIL", name, "the generated AGENTS.md is not in the prompt; check AGENTS.override.md and project_doc_max_bytes"))
        else:
            checks.append(("ok", name, "profile loads" + (" and AGENTS.md reaches the prompt" if digest else "")))
    return checks


def check_rules(bin_path: Path | None, home: Path, cwd: Path) -> list[Check]:
    files = sorted(f for f in (home / "rules").glob("*.rules") if f.is_file()) if (home / "rules").is_dir() else []
    if not files:
        return [("ok", "rules load", "no rules files")]
    if bin_path is None:
        return [("warn", "rules load", "codex not found; skipped")]
    r = run_codex(bin_path, home, ["execpolicy", "check", *[a for f in files for a in ("--rules", str(f))], "true"], cwd, 60)
    if isinstance(r, str):
        return [("FAIL", "rules load", r)]
    if r.returncode != 0:
        return [("FAIL", "rules load", f"Codex drops every rule, default.rules included, when one file fails: {_error(r)}")]
    return [("ok", "rules load", f"{len(files)} files in {home / 'rules'} load")]


def parse_summary(stderr: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in stderr.splitlines():
        m = SUMMARY.match(ANSI.sub("", line).strip())
        if m and m.group(1) not in out:
            out[m.group(1)] = m.group(2).strip()
    return out


def check_live(bin_path: Path | None, home: Path, cwd: Path, ts: list[Tier]) -> list[Check]:
    if bin_path is None:
        return [("FAIL", "live probe", "codex not found")]
    checks = []
    for t in ts:
        name = f"tier {t.name} live"
        r = run_codex(bin_path, home, ["exec", "--profile", t.name, "--ephemeral", "--sandbox", "read-only",
                                       "--skip-git-repo-check", "Reply with the single word OK."], cwd, 300)
        if isinstance(r, str):
            checks.append(("FAIL", name, r))
            continue
        got = parse_summary(r.stderr)
        if got.get("model") == t.model and got.get("reasoning effort") == t.effort:
            checks.append(("ok", name, f"started {t.model} at {t.effort}"))
        else:
            want = {"model": t.model, "reasoning effort": t.effort}
            checks.append(("FAIL", name, f"expected {want}, codex reported {got or _error(r)}"))
    return checks
