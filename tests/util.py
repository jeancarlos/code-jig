import os
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path


def tree(test: unittest.TestCase) -> Path:
    base = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, base, True)
    if not hasattr(test, "_state_patch"):
        data = base / "state data"
        test._state_patch = mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(data), "LOCALAPPDATA": str(data)})
        test._state_patch.start()
        test.addCleanup(test._state_patch.stop)
    root = base / "dir with space" / "ação"
    root.mkdir(parents=True)
    return root


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path

