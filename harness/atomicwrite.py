import contextlib
import os
import stat
import tempfile
from pathlib import Path


def resolve_inside(path: str, root: str | os.PathLike[str] | None = None) -> Path | None:
    """The real path of `path` when it is a regular file, not a symlink, inside `root`.

    `root` defaults to the working directory; a relative `path` is taken from it.
    Anything else (symlink, directory, device, missing file, a path that escapes
    the root) gives None, so callers never touch files they were not handed.
    """
    base = Path(os.path.realpath(root if root is not None else os.getcwd()))
    p = Path(path)
    if not p.is_absolute():
        p = base / p
    try:
        st = os.lstat(p)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    real = Path(os.path.realpath(p))
    return real if real.is_relative_to(base) else None


def atomic_write(target: Path, data: bytes, mode: int | None = None) -> None:
    """Replace `target` with `data` without a window where it is partial or wider-permissioned.

    The temp file gets an unpredictable name (mkstemp, O_EXCL) in the target's own
    directory, so os.replace stays on one filesystem and nobody can pre-plant it.
    It keeps the target's permission bits, or `mode` for a new file.
    """
    if mode is None:
        mode = stat.S_IMODE(os.stat(target).st_mode) if target.exists() else 0o600
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
