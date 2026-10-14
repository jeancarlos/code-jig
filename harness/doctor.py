import mmap
import os
import shutil
from pathlib import Path

Check = tuple[str, str, str]

PACK_KEYS = (
    "project_doc_max_bytes",
    "approvals_reviewer",
    "model_auto_compact_token_limit",
    "tool_output_token_limit",
)
SHIM_MAX_BYTES = 1_000_000


def resolve_codex_bin(arg: str | None) -> Path | None:
    value = arg or os.environ.get("CODEX_BIN") or shutil.which("codex")
    return Path(value) if value else None


def check_binary(bin_path: Path | None, keys=PACK_KEYS) -> list[Check]:
    name = "codex keys"
    if bin_path is None or not bin_path.is_file():
        return [("FAIL", name, "codex binary not found; pass --codex-bin PATH or set CODEX_BIN")]
    if bin_path.stat().st_size < SHIM_MAX_BYTES:
        return [("FAIL", name, f"{bin_path} is a launcher, not the native binary; pass --codex-bin PATH")]
    with open(bin_path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
        missing = [k for k in keys if m.find(k.encode()) == -1]
    if missing:
        return [("FAIL", name, f"not in {bin_path.name}: {', '.join(missing)}")]
    return [("ok", name, f"{len(keys)} keys present in {bin_path.name}")]


def report(checks: list[Check]) -> int:
    for level, name, detail in checks:
        print(f"{level} {name}: {detail}")
    return 1 if any(c[0] == "FAIL" for c in checks) else 0
