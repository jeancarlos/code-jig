import io
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from build_release import TAG, archive

from codejig import VERSION
from codejig.install import release_digest

DATA = ("core", "skills", "bench")


def stage(tag: str, root: Path) -> None:
    zipfile.ZipFile(io.BytesIO(archive())).extractall(root)
    core = root / "codejig" / "_core"
    core.mkdir()
    for name in DATA:
        shutil.move(root / name, core / name)
    (core / "VERSION").write_text(f"{tag}\n{release_digest(core)}\n", encoding="utf-8", newline="\n")


def build(tag: str, out: Path) -> None:
    if not TAG.fullmatch(tag) or tag != f"v{VERSION}":
        raise SystemExit(f"build_wheel: tag {tag} does not match code-jig VERSION {VERSION}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stage(tag, root)
        subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(out), str(root)],
                       check=True)


if __name__ == "__main__":
    build(sys.argv[1], Path(sys.argv[2]))
