import json
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tier:
    name: str
    model: str
    effort: str


def read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ValueError(f"{path}: not found") from None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"{path}: {e}") from e


def _strings(path: Path, data: dict) -> dict:
    bad = [k for k, v in data.items() if not isinstance(v, str) or not v.strip()]
    if bad:
        raise ValueError(f"{path}: {', '.join(bad)} must be a non-empty string")
    return data


def load(core: Path, overlay_root: Path) -> list[Tier]:
    efforts_path = core / "core" / "tiers.toml"
    models_path = overlay_root / "profiles.toml"
    efforts = _strings(efforts_path, read_toml(efforts_path))
    models = _strings(models_path, read_toml(models_path))
    missing = [t for t in efforts if t not in models]
    if missing:
        raise ValueError(f"{models_path}: no model for tier {', '.join(missing)}")
    unknown = [t for t in models if t not in efforts]
    if unknown:
        raise ValueError(f"{models_path}: unknown tier {', '.join(unknown)}; tiers are {', '.join(efforts)}")
    return [Tier(name, models[name], effort) for name, effort in efforts.items()]


def extra_policy(overlay_root: Path) -> str:
    path = overlay_root / "guardian-policy.md"
    return path.read_text(encoding="utf-8-sig").strip() if path.is_file() else ""


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False).replace("\x7f", "\\u007f")


def profile_body(tier: Tier, policy: str) -> str:
    lines = [
        f"model = {toml_str(tier.model)}",
        f"model_reasoning_effort = {toml_str(tier.effort)}",
        'approvals_reviewer = "auto_review"',
    ]
    if policy:
        lines += ["", "[auto_review]", f"extra_policy = {toml_str(policy)}"]
    return "\n".join(lines) + "\n"
