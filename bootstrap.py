import argparse
import hashlib
import io
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = "https://setup-harness.jeansouza.dev"
REPO = "jeancarlos/codex-harness"
ZIP = "codex-harness.zip"
SUMS = "SHA256SUMS"
TAG = re.compile(r"v\d+\.\d+\.\d+")
TIMEOUT = 30
MAX_ZIP = 50 * 1024 * 1024
MAX_SUMS = 64 * 1024
MAX_TREE = 200 * 1024 * 1024
NO_ZIP = "releases before v0.11.0 have no zip; bump core_version"
RESERVED = {"con", "prn", "aux", "nul"} | {p + str(n) for p in ("com", "lpt") for n in range(1, 10)}


class Refused(Exception):
    pass


def valid_tag(value):
    if not isinstance(value, str) or not TAG.fullmatch(value):
        raise Refused(f"{value!r} is not a release tag like v1.2.3")
    return value


def release_digest(root):
    h = hashlib.sha256()
    files = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if p.is_file() and "__pycache__" not in rel.parts and rel.as_posix() != "VERSION":
            files.append((rel.as_posix(), p))
    for rel, p in sorted(files):
        h.update(rel.encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def read_version(root):
    try:
        words = (root / "VERSION").read_text(encoding="utf-8").split()
    except (OSError, ValueError):
        return "", ""
    words += ["", ""]
    return words[0], words[1]


def verify_tree(root, tag):
    found, digest = read_version(root)
    if found != tag or not digest or digest != release_digest(root):
        raise Refused(f"{root} does not match release {tag}; delete it and rerun")


def check_names(zf):
    seen = set()
    total = 0
    for info in zf.infolist():
        name = info.filename
        parts = name[:-1].split("/") if name.endswith("/") else name.split("/")
        if not name or "\\" in name or ":" in name or name.startswith("/") or any(p in ("", ".", "..") for p in parts):
            raise Refused(f"unsafe archive entry {name!r}")
        if any(p.split(".")[0].lower() in RESERVED or p != p.rstrip(". ") for p in parts):
            raise Refused(f"archive entry {name!r} is not a portable Windows name")
        mode = info.external_attr >> 16
        if stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise Refused(f"archive entry {name!r} is not a regular file")
        key = "/".join(parts).lower()
        if key in seen:
            raise Refused(f"archive entry {name!r} collides with another entry")
        seen.add(key)
        total += info.file_size
    if total > MAX_TREE:
        raise Refused(f"the archive unpacks to more than {MAX_TREE} bytes")


def unpack(data, target, tag):
    zf = zipfile.ZipFile(io.BytesIO(data))
    check_names(zf)
    tmp = Path(tempfile.mkdtemp(prefix=f".{tag}-", dir=target.parent))
    try:
        base = tmp.resolve()
        for info in zf.infolist():
            if not (tmp / info.filename).resolve().is_relative_to(base):
                raise Refused(f"archive entry {info.filename!r} escapes the target")
        zf.extractall(tmp)
        verify_tree(tmp, tag)
        try:
            os.rename(tmp, target)
        except OSError:
            if not target.is_dir():
                raise
            shutil.rmtree(tmp, ignore_errors=True)
            verify_tree(target, tag)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def write_atomic(path, text, mode=0o644, newline="\n"):
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
