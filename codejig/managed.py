# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import os
import sys
import tomllib
from pathlib import Path

from codejig.tiers import Tier

Check = tuple[str, str, str]


def requirements_path() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "OpenAI" / "Codex" / "requirements.toml"
    return Path("/etc/codex/requirements.toml")


def _read_here(path: Path, name: str) -> tuple[dict, list[Check]]:
    if not path.is_file():
        return {}, [("ok", name, f"none at {path}; cloud-delivered requirements are not visible to doctor")]
    try:
        here = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        return {}, [("FAIL", name, f"{path}: {e}")]
    return here, [("ok", name, f"read {path}; cloud-delivered requirements are not visible to doctor")]


def _policy_checks(here: dict, ts: list[Tier]) -> list[Check]:
    checks: list[Check] = []
    reviewers = here.get("allowed_approvals_reviewers")
    if isinstance(reviewers, list) and "auto_review" not in reviewers:
        checks.append(("FAIL", "guardian allowed", f"allowed_approvals_reviewers = {reviewers}; the tier profiles need auto_review"))
    auto_review = here.get("auto_review") if isinstance(here.get("auto_review"), dict) else {}
    ignored = auto_review.get("ignore_rules") if isinstance(auto_review.get("ignore_rules"), list) else []
    hit = sorted({t.model for t in ts} & {m for m in ignored if isinstance(m, str)})
    if hit:
        checks.append(("warn", "overlay rules", f"auto_review.ignore_rules lists {', '.join(hit)}; allow rules do nothing for those models"))
    if here.get("allow_managed_hooks_only") is True:
        checks.append(("warn", "hooks", "allow_managed_hooks_only = true; the pack's hooks will not run"))
    if here.get("guardian_extra_policy"):
        checks.append(("warn", "guardian policy", "managed guardian_extra_policy replaces the overlay guardian-policy.md"))
    return checks


def _bench_diff(here: dict, bench: Path) -> Check:
    try:
        sim = tomllib.loads(bench.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return ("warn", "bench diff", f"{bench}: {e}")
    parts = []
    if only_here := sorted(set(here) - set(sim)):
        parts.append(f"locked here, not simulated: {', '.join(only_here)}")
    if only_bench := sorted(set(sim) - set(here)):
        parts.append(f"simulated, not locked here: {', '.join(only_bench)}")
    if changed := sorted(k for k in set(here) & set(sim) if here[k] != sim[k]):
        parts.append(f"different values: {', '.join(changed)}")
    return ("warn", "bench diff", "; ".join(parts)) if parts else ("ok", "bench diff", "matches bench/requirements.toml")


def check_requirements(path: Path, bench: Path, ts: list[Tier]) -> list[Check]:
    name = "managed requirements"
    here, checks = _read_here(path, name)
    if checks[0][0] == "FAIL":
        return checks
    return checks + _policy_checks(here, ts) + [_bench_diff(here, bench)]
