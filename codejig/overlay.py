import tomllib
from dataclasses import dataclass
from pathlib import Path

REQUIRED = ("core_version", "core_writable")


@dataclass(frozen=True)
class Overlay:
    root: Path
    core_version: str
    core_writable: bool
    auto_compact_token_limit: int | None = None
    git_gate: bool = False
    prose_gate: bool = False
    push_cleanup: bool | None = None


def load(root: Path) -> Overlay:
    path = root / "overlay.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"{path}: {e}") from e
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ValueError(f"{path}: missing {', '.join(missing)}")
    if not isinstance(data["core_writable"], bool):
        raise ValueError(f"{path}: core_writable must be true or false")
    compact = data.get("auto_compact_token_limit")
    if compact is not None and (isinstance(compact, bool) or not isinstance(compact, int) or compact <= 0):
        raise ValueError(f"{path}: auto_compact_token_limit must be a positive integer")
    flags = {k: data.get(k, False) for k in ("git_gate", "prose_gate")}
    flags["push_cleanup"] = data.get("push_cleanup")
    bad = [k for k, v in flags.items() if not isinstance(v, bool) and not (k == "push_cleanup" and v is None)]
    if bad:
        raise ValueError(f"{path}: {', '.join(bad)} must be true or false")
    return Overlay(root, str(data["core_version"]), data["core_writable"], compact, **flags)
