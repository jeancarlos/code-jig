import os
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent


def codex_home(arg: str | None) -> Path:
    return Path(arg or os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def overlay_dir(arg: str | None) -> Path:
    value = arg or os.environ.get("CODEX_HARNESS_OVERLAY")
    if not value:
        raise SystemExit("harness: no overlay; pass --overlay PATH or set CODEX_HARNESS_OVERLAY")
    root = Path(value).expanduser().resolve()
    if not (root / "overlay.toml").is_file():
        raise SystemExit(f"harness: {root / 'overlay.toml'} not found")
    return root


def agents_skills() -> Path:
    return Path(os.environ.get("CODEX_HARNESS_SKILLS_DIR") or Path.home() / ".agents" / "skills").expanduser()
