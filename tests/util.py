import shutil
import tempfile
import unittest
from pathlib import Path


def tree(test: unittest.TestCase) -> Path:
    base = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, base, True)
    root = base / "dir with space" / "ação"
    root.mkdir(parents=True)
    return root


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path

