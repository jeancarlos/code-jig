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
    return Overlay(root, str(data["core_version"]), data["core_writable"], compact)
