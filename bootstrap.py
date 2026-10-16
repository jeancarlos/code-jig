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

BASE_URL = "https://code-jig.jeansouza.dev"
REPO = "jeancarlos/code-jig"
ZIP = "code-jig.zip"
SUMS = "SHA256SUMS"
TAG = re.compile(r"v\d+\.\d+\.\d+", re.ASCII)
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
        if "__pycache__" in parts:
            raise Refused(f"archive entry {name!r} is undigested bytecode")
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


OWN = "# written by code-jig bootstrap"
PIN = re.compile(r"(?m)^core_version\s*=.*$")
SCP = re.compile(r"[\w.-]+@[\w.-]+:\S+")
CLONE_CONFIG = ["-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=never"]


def classify(value):
    if value.startswith("-"):
        raise Refused("the overlay looks like an option")
    parts = urllib.parse.urlsplit(value)
    if parts.scheme in ("https", "ssh"):
        if parts.password or (parts.scheme == "https" and parts.username):
            raise Refused("put credentials in a git credential helper or SSH key, not in the overlay URL")
        return "git"
    if SCP.fullmatch(value):
        return "git"
    if "::" in value:
        raise Refused("transport helpers are not allowed in the overlay; use https://, ssh:// or user@host:path")
    if "://" in value:
        raise Refused(f"unsupported overlay URL scheme {parts.scheme!r}; use https://, ssh:// or user@host:path")
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


MARK = "code-jig launcher "


def sh_launcher(python, core, overlay, tag):
    q = shlex.quote
    return (f"#!/bin/sh\n# {MARK}{tag}\nPYTHONPATH={q(str(core))}\nCODE_JIG_OVERLAY={q(str(overlay))}\n"
            f"export PYTHONPATH CODE_JIG_OVERLAY\nexec {q(python)} -P -s -m codejig \"$@\"\n")


def cmd_escape(value):
    return str(value).replace("%", "%%")


def cmd_launcher(python, core, overlay, tag):
    return ("@echo off\n"
            f"rem {MARK}{tag}\n"
            "setlocal\n"
            "for /f \"tokens=2 delims=:.\" %%c in ('chcp') do set \"CODE_JIG_CP=%%c\"\n"
            "chcp 65001 >nul\n"
            f"set \"PYTHONPATH={cmd_escape(core)}\"\n"
            f"set \"CODE_JIG_OVERLAY={cmd_escape(overlay)}\"\n"
            f"\"{cmd_escape(python)}\" -P -s -m codejig %*\n"
            "set \"CODE_JIG_RC=%ERRORLEVEL%\"\n"
            "chcp %CODE_JIG_CP% >nul\n"
            "exit /b %CODE_JIG_RC%\n")


def launcher_paths(bin_dir):
    ext = ".cmd" if os.name == "nt" else ""
    return [bin_dir / ("code-jig" + ext), bin_dir / ("cjig" + ext)]


def check_launcher(path):
    if path.exists() and MARK not in path.read_text(encoding="utf-8", errors="replace"):
        raise Refused(f"{path} was not written by this bootstrap; move it away and rerun")


def write_launcher(bin_dir, python, core, overlay, tag):
    paths = launcher_paths(bin_dir)
    for path in paths:
        check_launcher(path)
    bin_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if os.name == "nt":
            write_atomic(path, cmd_launcher(python, core, overlay, tag), mode=0o755, newline="\r\n")
        else:
            write_atomic(path, sh_launcher(python, core, overlay, tag), mode=0o755)
    return paths


def hint_lines(bin_dir, flavour):
    if flavour == "nt":
        quoted = str(bin_dir).replace("'", "''")
        return [
            "to run code-jig by name, run this line once in PowerShell:",
            f"[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path', 'User') + ';{quoted}', 'User')",
        ]
    return [
        "to run code-jig by name, add this line to your shell profile:",
        f"export PATH={shlex.quote(str(bin_dir))}:$PATH",
    ]


def path_hint(bin_dir):
    want = os.path.normcase(os.path.abspath(bin_dir))
    dirs = [os.path.normcase(os.path.abspath(p)) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    if want not in dirs:
        first, line = hint_lines(bin_dir, os.name)
        print(f"bootstrap: {bin_dir} is not on PATH; {first}")
        print(line)


def parse_args(argv):
    p = argparse.ArgumentParser(prog="bootstrap.py", description="Install code-jig from a release.")
    p.add_argument("--overlay", help="overlay folder or git URL")
    p.add_argument("--overlay-dir", help="where a cloned or new overlay goes (default ~/code-jig-overlay)")
    p.add_argument("--version", help="vX.Y.Z or latest")
    p.add_argument("--base-url", default=BASE_URL)
    p.add_argument("--repo", default=REPO)
    p.add_argument("--codex-bin")
    p.add_argument("--codex-home")
    p.add_argument("--data-dir")
    p.add_argument("--bin-dir")
    return p.parse_args(argv)


def data_dir(arg):
    if arg:
        return Path(arg).expanduser().absolute()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "code-jig"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "code-jig"


def bin_dir(arg, data):
    if arg:
        return Path(arg).expanduser().absolute()
    return data / "bin" if os.name == "nt" else Path.home() / ".local" / "bin"


def interpreter():
    return getattr(sys, "_base_executable", None) or sys.executable


def run_install(python, core, overlay, codex_home):
    env = dict(os.environ, PYTHONPATH=str(core), CODE_JIG_OVERLAY=str(overlay))
    home = ["--codex-home", codex_home] if codex_home else []
    return subprocess.run([python, "-P", "-s", "-m", "codejig", *home, "install"], env=env).returncode


def run_doctor(python, core, overlay, codex_home, codex_bin):
    env = dict(os.environ, PYTHONPATH=str(core), CODE_JIG_OVERLAY=str(overlay))
    home = ["--codex-home", codex_home] if codex_home else []
    binary = ["--codex-bin", codex_bin] if codex_bin else []
    if subprocess.run([python, "-P", "-s", "-m", "codejig", *home, "doctor", *binary], env=env).returncode:
        print("bootstrap: installed; doctor reported problems above")


def run(args):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
        raise Refused(f"--repo {args.repo!r} must look like owner/name")
    if not allowed(args.base_url):
        raise Refused(f"--base-url {args.base_url} must be https")
    data = data_dir(args.data_dir)
    bins = bin_dir(args.bin_dir, data)
    for path in launcher_paths(bins):
        check_launcher(path)
    dest = Path(args.overlay_dir).expanduser().absolute() if args.overlay_dir else Path.home() / "code-jig-overlay"
    overlay = resolve_overlay(args.overlay or os.environ.get("CODE_JIG_OVERLAY"), dest)
    tag = choose_tag(args.version, overlay, args.repo)
    core = get_core(tag, data, args.base_url, args.repo)
    if overlay is None:
        overlay = create_overlay(core, dest, tag)
    python = interpreter()
    rc = run_install(python, core, overlay, args.codex_home)
    if rc:
        print(f"bootstrap: code-jig install failed with exit code {rc}; the launcher was not changed", file=sys.stderr)
        return rc
    if owned(overlay) and read_pin(overlay) != tag:
        write_pin(overlay, tag)
    for launcher in write_launcher(bins, python, core, overlay, tag):
        print(f"bootstrap: wrote {launcher}")
    path_hint(bins)
    run_doctor(python, core, overlay, args.codex_home, args.codex_bin)
    return 0


def missing_requirements() -> list[str]:
    lines = []
    if sys.version_info < (3, 11):
        lines.append("Python 3.11 or newer")
    if not shutil.which("git"):
        lines.append("git (Fedora: sudo dnf install git; Debian/Ubuntu: sudo apt install git; macOS: xcode-select --install; Windows: winget install --id Git.Git -e)")
    return lines


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    print("code-jig bootstrap", flush=True)
    args = parse_args(argv)
    missing = missing_requirements()
    for line in missing:
        print(f"missing requirement: {line}", file=sys.stderr)
    if missing:
        return 2
    try:
        return run(args)
    except Refused as e:
        print(f"bootstrap: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
