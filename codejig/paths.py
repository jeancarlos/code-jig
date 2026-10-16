import os
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent


def codex_home(arg: str | None) -> Path:
    return Path(arg or os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def state_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "code-jig"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "code-jig"


def overlay_dir(arg: str | None) -> Path:
    value = arg or os.environ.get("CODE_JIG_OVERLAY")
    if not value:
        raise SystemExit("code-jig: no overlay; pass --overlay PATH or set CODE_JIG_OVERLAY")
    root = Path(value).expanduser().absolute()
    if not (root / "overlay.toml").is_file():
        raise SystemExit(f"code-jig: {root / 'overlay.toml'} not found")
    return root


def agents_skills() -> Path:
    return Path(os.environ.get("CODE_JIG_SKILLS_DIR") or Path.home() / ".agents" / "skills").expanduser()


def claude_code_settings() -> Path | None:
    path = Path.home() / ".claude" / "settings.json"
    return path if path.is_file() else None
