import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from codejig import VERSION
from codejig.install import release_digest

ROOT = Path(__file__).resolve().parents[2]


def archive(*extra: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), "archive", "--format=zip", "--worktree-attributes", *extra, "HEAD"],
                          check=True, capture_output=True).stdout


def build(tag: str, out: Path) -> None:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or tag != f"v{VERSION}":
        raise SystemExit(f"build_release: tag {tag} does not match code-jig VERSION {VERSION}")
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(io.BytesIO(archive())).extractall(tmp)
        digest = release_digest(Path(tmp))
    blob = archive(f"--add-virtual-file=VERSION:{tag}\n{digest}\n")
    out.mkdir(parents=True, exist_ok=True)
    (out / "code-jig.zip").write_bytes(blob)
    (out / "SHA256SUMS").write_text(f"{hashlib.sha256(blob).hexdigest()}  code-jig.zip\n", encoding="utf-8",
                                    newline="\n")
    shutil.copyfile(ROOT / "bootstrap.py", out / "bootstrap.py")


if __name__ == "__main__":
    build(sys.argv[1], Path(sys.argv[2]))
