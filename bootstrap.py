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


def allowed(url):
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost"))


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            raise Refused(f"refusing a redirect to {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, limit):
    if not allowed(url):
        raise Refused(f"refusing {url}: only https")
    with urllib.request.build_opener(Redirects).open(url, timeout=TIMEOUT) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise Refused(f"{url} is larger than {limit} bytes")
    return data


def fetch_asset(tag, name, base, repo, limit):
    primary = f"{base.rstrip('/')}/v/{tag}/{name}"
    try:
        return fetch(primary, limit)
    except urllib.error.HTTPError as e:
        e.close()
        if e.code == 404:
            raise Refused(f"{tag} has no {name}; {NO_ZIP}")
        if e.code < 500:
            raise Refused(f"{primary}: HTTP {e.code}")
        reason = f"HTTP {e.code}"
    except OSError as e:
        reason = str(e)
    fallback = f"https://github.com/{repo}/releases/download/{tag}/{name}"
    print(f"bootstrap: {primary} failed ({reason}); trying {fallback}", file=sys.stderr)
    try:
        return fetch(fallback, limit)
    except urllib.error.HTTPError as e:
        e.close()
        raise Refused(f"{fallback}: HTTP {e.code}" + (f"; {NO_ZIP}" if e.code == 404 else ""))
    except OSError as e:
        raise Refused(f"{fallback}: {e}")


def resolve_latest(repo):
    url = f"https://github.com/{repo}/releases/latest"
    try:
        urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, method="HEAD"), timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        e.close()
        found = re.search(r"/tag/([^/]+)$", e.headers.get("Location", "") or "")
        if e.code in (301, 302, 303, 307, 308) and found:
            return valid_tag(found.group(1))
        raise Refused(f"{url}: HTTP {e.code}")
    except OSError as e:
        raise Refused(f"{url}: {e}")
    raise Refused(f"{url} did not redirect to a release tag")


def parse_sums(data):
    for line in data.decode("ascii", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == ZIP and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            return parts[0]
    raise Refused(f"{SUMS} has no line for {ZIP}")


def get_core(tag, data, base, repo):
    target = data / tag
    if target.exists():
        verify_tree(target, tag)
        print(f"bootstrap: reusing {target}")
        return target
    data.mkdir(parents=True, exist_ok=True)
    expected = parse_sums(fetch_asset(tag, SUMS, base, repo, MAX_SUMS))
    blob = fetch_asset(tag, ZIP, base, repo, MAX_ZIP)
    if hashlib.sha256(blob).hexdigest() != expected:
        raise Refused(f"{ZIP} for {tag} does not match {SUMS}")
    unpack(blob, target, tag)
    print(f"bootstrap: unpacked {tag} into {target}")
    return target


OWN = "# written by codex-harness bootstrap"
PIN = re.compile(r"(?m)^core_version\s*=.*$")
SCP = re.compile(r"[\w.-]+@[\w.-]+:\S+")
CLONE_CONFIG = ["-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=never"]


def classify(value):
    if value.startswith("-"):
        raise Refused(f"overlay {value!r} looks like an option")
    parts = urllib.parse.urlsplit(value)
    if parts.scheme in ("https", "ssh"):
        if parts.password or (parts.scheme == "https" and parts.username):
            raise Refused("put credentials in a git credential helper or SSH key, not in the overlay URL")
        return "git"
    if SCP.fullmatch(value):
        return "git"
    if "::" in value or "://" in value:
        raise Refused(f"unsupported overlay URL {value!r}; use https://, ssh:// or user@host:path")
    return "path"


def git_run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    except OSError as e:
        raise Refused(f"git is needed to clone the overlay: {e}")


def clone(url, dest):
    if dest.exists():
        origin = git_run(["git", "-C", str(dest), "config", "--get", "remote.origin.url"])
        if origin.returncode or origin.stdout.strip() != url:
            raise Refused(f"{dest} exists and is not a clone of that URL; pass --overlay-dir")
        cmd = ["git", "-C", str(dest), "pull", "--ff-only"]
    else:
        cmd = ["git", *CLONE_CONFIG, "clone", "--", url, str(dest)]
    try:
        done = subprocess.run(cmd)
    except OSError as e:
        raise Refused(f"git is needed to clone the overlay: {e}")
    if done.returncode:
        raise Refused(f"git could not fetch the overlay into {dest} (exit {done.returncode})")


def resolve_overlay(value, dest):
    if value:
        if classify(value) == "git":
            clone(value, dest)
            path = dest
        else:
            path = Path(value).expanduser().absolute()
        if not (path / "overlay.toml").is_file():
            raise Refused(f"{path / 'overlay.toml'} not found")
        return path
    if (dest / "overlay.toml").is_file():
        return dest
    if dest.exists():
        raise Refused(f"{dest} exists but holds no overlay.toml; pass --overlay or --overlay-dir")
    return None


def read_pin(overlay):
    import tomllib
    path = overlay / "overlay.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise Refused(f"{path}: {e}")
    return valid_tag(str(data.get("core_version", "")))


def owned(overlay):
    if (overlay / ".git").exists():
        return False
    try:
        with open(overlay / "overlay.toml", encoding="utf-8") as f:
            return f.readline().rstrip("\r\n") == OWN
    except (OSError, ValueError):
        return False


def write_pin(overlay, tag):
    path = overlay / "overlay.toml"
    write_atomic(path, PIN.sub(f'core_version = "{tag}"', path.read_text(encoding="utf-8"), count=1))


def create_overlay(core, dest, tag):
    shutil.copytree(core / "overlay-examples" / "release", dest)
    path = dest / "overlay.toml"
    body = PIN.sub(f'core_version = "{tag}"', path.read_text(encoding="utf-8"), count=1)
    write_atomic(path, OWN + "\n" + body)
    print(f"bootstrap: wrote overlay {dest}")
    return dest


def resolve(version, repo):
    return resolve_latest(repo) if version == "latest" else valid_tag(version)


def choose_tag(version, overlay, repo):
    if overlay is None:
        return resolve(version or "latest", repo)
    pin = read_pin(overlay)
    if not version or version == pin:
        return pin
    if not owned(overlay):
        raise Refused(f"--version {version} differs from core_version {pin} in {overlay}; bump core_version in your overlay")
    return resolve(version, repo)


MARK = "codex-harness launcher "


def sh_launcher(python, core, overlay, tag):
    q = shlex.quote
    return (f"#!/bin/sh\n# {MARK}{tag}\nPYTHONPATH={q(str(core))}\nCODEX_HARNESS_OVERLAY={q(str(overlay))}\n"
            f"export PYTHONPATH CODEX_HARNESS_OVERLAY\nexec {q(python)} -P -s -m harness \"$@\"\n")


def cmd_escape(value):
    return str(value).replace("%", "%%")


def cmd_launcher(python, core, overlay, tag):
    return ("@echo off\n"
            f"rem {MARK}{tag}\n"
            "setlocal\n"
            "for /f \"tokens=2 delims=:.\" %%c in ('chcp') do set \"HARNESS_CP=%%c\"\n"
            "chcp 65001 >nul\n"
            f"set \"PYTHONPATH={cmd_escape(core)}\"\n"
            f"set \"CODEX_HARNESS_OVERLAY={cmd_escape(overlay)}\"\n"
            f"\"{cmd_escape(python)}\" -P -s -m harness %*\n"
            "set \"HARNESS_RC=%ERRORLEVEL%\"\n"
            "chcp %HARNESS_CP% >nul\n"
            "exit /b %HARNESS_RC%\n")


def launcher_path(bin_dir):
    return bin_dir / ("harness.cmd" if os.name == "nt" else "harness")


def check_launcher(path):
    if path.exists() and MARK not in path.read_text(encoding="utf-8", errors="replace"):
        raise Refused(f"{path} was not written by this bootstrap; move it away and rerun")


def write_launcher(bin_dir, python, core, overlay, tag):
    path = launcher_path(bin_dir)
    check_launcher(path)
    bin_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        write_atomic(path, cmd_launcher(python, core, overlay, tag), mode=0o755, newline="\r\n")
    else:
        write_atomic(path, sh_launcher(python, core, overlay, tag), mode=0o755)
    return path


def path_hint(bin_dir):
    want = os.path.normcase(os.path.abspath(bin_dir))
    dirs = [os.path.normcase(os.path.abspath(p)) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    if want not in dirs:
        print(f"bootstrap: {bin_dir} is not on PATH; add it to run harness by name")
