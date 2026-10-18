import contextlib
import os
import secrets
import stat
import tempfile
from pathlib import Path

DIR_FDS = (os.open in os.supports_dir_fd and os.rename in os.supports_dir_fd
           and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"))


_FILE_LIST_DIRECTORY = 0x1
_FILE_SHARE_READ_WRITE = 0x1 | 0x2
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000


class Changed(OSError):
    pass


class HardLinked(Changed, ValueError):
    pass


def _win_open_dir(path: str) -> int:
    """A descriptor for the folder at `path` itself, never what a link or junction there points at.
    It is opened without FILE_SHARE_DELETE, so while it is open nobody can rename, delete or
    replace that folder."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    handle = kernel32.CreateFileW(path, _FILE_LIST_DIRECTORY, _FILE_SHARE_READ_WRITE, None, _OPEN_EXISTING,
                                  _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    return msvcrt.open_osfhandle(handle, os.O_RDONLY)


_open_dir = _win_open_dir if os.name == "nt" else None


def _refuse_hard_link(path, st: os.stat_result | None) -> None:
    if st is not None and st.st_nlink > 1:
        raise HardLinked(f"{path} has {st.st_nlink} hard links; left as it is: a replace would give this name a new file "
                         "and silently cut it off from the other names, which keep the old content, so a write meant "
                         "for one path would not reach the others")


class Inside(type(Path())):
    """A regular file that resolve_inside found inside `root`.

    Reading it and atomic_write on it refuse a file or folder swapped since that check:
    with directory fds (POSIX) they walk down from root with O_NOFOLLOW and write
    relative to the opened folder; elsewhere they check the real path again just
    before reading and before the replace, and on Windows a write holds every folder
    from root down open, refusing a link or junction, so none can be moved or replaced
    until the replace is done. A write also refuses when the file no longer holds what
    read_bytes returned. An edit landing between that last check and the replace is
    still overwritten. Paths derived from it are plain paths.
    """

    checked_root = None
    checked_parts = ()
    checked_id = None
    read_data = None

    def with_segments(self, *segments):
        return Path(*segments)

    def _walk(self) -> int:
        fd = os.open(self.checked_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in self.checked_parts[:-1]:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _check(self, st: os.stat_result) -> None:
        if not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != self.checked_id:
            raise Changed(f"{self} was replaced after it was checked; left as it is")

    def _read_at(self, dfd: int) -> bytes:
        fd = os.open(self.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
        with os.fdopen(fd, "rb") as f:
            self._check(os.fstat(f.fileno()))
            return f.read()

    @contextlib.contextmanager
    def _held(self):
        fds = []
        try:
            if _open_dir is not None:
                folder = self.checked_root
                for part in (None, *self.checked_parts[:-1]):
                    folder = folder if part is None else os.path.join(folder, part)
                    fds.append(_open_dir(folder))
                    st = os.fstat(fds[-1])
                    if not stat.S_ISDIR(st.st_mode) or getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        raise Changed(f"{folder} is now a link or junction; left {self} as it is")
            yield
        finally:
            for fd in fds:
                os.close(fd)

    def _guard(self) -> None:
        if os.path.realpath(self) != str(self):
            raise Changed(f"{self} now resolves elsewhere; left as it is")
        self._check(os.lstat(self))

    def read_bytes(self) -> bytes:
        if self.checked_id is None:
            return super().read_bytes()
        if DIR_FDS:
            dfd = self._walk()
            try:
                data = self._read_at(dfd)
            finally:
                os.close(dfd)
        else:
            self._guard()
            data = super().read_bytes()
        self.read_data = data
        return data

    def _unchanged(self, current: bytes) -> None:
        if self.read_data is not None and current != self.read_data:
            raise Changed(f"{self} changed while it was being rewritten; left as it is")


def resolve_inside(path: str, root: str | os.PathLike[str] | None = None) -> Inside | None:
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
    if not real.is_relative_to(base):
        return None
    found = Inside(real)
    found.checked_root, found.checked_parts, found.checked_id = str(base), real.relative_to(base).parts, (st.st_dev, st.st_ino)
    return found


def _write_at(target: Inside, data: bytes, mode: int | None) -> None:
    dfd = target._walk()
    try:
        target._unchanged(target._read_at(dfd))
        st = os.stat(target.name, dir_fd=dfd, follow_symlinks=False)
        _refuse_hard_link(target, st)
        tmp = f".{target.name}.{secrets.token_hex(8)}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
                os.fchmod(f.fileno(), stat.S_IMODE(st.st_mode) if mode is None else mode)
            st = os.stat(target.name, dir_fd=dfd, follow_symlinks=False)
            target._check(st)
            _refuse_hard_link(target, st)
            target._unchanged(target._read_at(dfd))
            os.rename(tmp, target.name, src_dir_fd=dfd, dst_dir_fd=dfd)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp, dir_fd=dfd)
            raise
    finally:
        os.close(dfd)


def atomic_write(target: Path, data: bytes, mode: int | None = None) -> None:
    """Replace `target` with `data` without a window where it is partial or wider-permissioned.

    The temp file gets an unpredictable name (O_EXCL) in the target's own directory,
    so the replace stays on one filesystem and nobody can pre-plant it. It keeps the
    target's permission bits, or `mode` for a new file. A target with more than one
    hard link is refused. A target from resolve_inside is written only while it is
    still the file that was checked and read.
    """
    inside = isinstance(target, Inside) and target.checked_id is not None
    if inside and DIR_FDS:
        _write_at(target, data, mode)
        return
    with target._held() if inside else contextlib.nullcontext():
        _replace(target, data, mode, inside)


def _existing(target: Path) -> os.stat_result | None:
    try:
        return os.stat(target)
    except FileNotFoundError:
        return None


def _replace(target: Path, data: bytes, mode: int | None, inside: bool) -> None:
    if inside:
        target._guard()
        target._unchanged(Path(target).read_bytes())
    st = _existing(target)
    _refuse_hard_link(target, st)
    if mode is None:
        mode = stat.S_IMODE(st.st_mode) if st else 0o600
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        if inside:
            target._guard()
            target._unchanged(Path(target).read_bytes())
        _refuse_hard_link(target, _existing(target))
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
