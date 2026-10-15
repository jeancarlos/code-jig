import os
import stat
import tempfile
from pathlib import Path


def safe_write_file(path: str, data: bytes) -> bool:
    """Atomic write with symlink and boundary checks.

    Creates temp with mkstemp (O_EXCL, unpredictable name), fchmod to original mode,
    writes, fsyncs, os.replace onto resolved target. Refuses symlinks and paths
    outside cwd. Returns True on success, False on error (logged to stderr).
    """
    try:
        p = Path(path)
        try:
            s = os.lstat(str(p))
            if stat.S_ISLNK(s.st_mode):
                return False
        except (OSError, FileNotFoundError):
            pass

        resolved = Path(os.path.realpath(str(p)))
        cwd = Path(os.getcwd()).resolve()
        if not str(resolved).startswith(str(cwd)):
            return False

        mode = None
        if p.exists():
            try:
                mode = p.stat().st_mode
            except (OSError, PermissionError):
                pass

        parent = resolved.parent
        parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=str(parent), prefix='.', suffix='.tmp')
        try:
            if mode is not None:
                os.fchmod(fd, mode)
            os.write(fd, data)
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp_path, str(p))
            return True
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return False
    except Exception:
        return False
