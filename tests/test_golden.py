import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from harness import install
from harness.overlay import load
from harness.paths import CORE
from tests.util import tree

RENAME: list[tuple[str, str]] = []
EXAMPLES = ("enterprise", "personal", "release")
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "golden"
KEPT = ("AGENTS.md", "hooks.json")


def rename(text: str) -> str:
    for old, new in RENAME:
        text = re.sub(old, new, text)
    return text


def _kept(rel: str) -> bool:
    return rel in KEPT or rel.endswith(".config.toml") or rel.split("/")[0] in ("agents", "rules", "skills")


def _normalize(text: str, home: Path) -> str:
    py = install.interpreter()
    for raw in (py, Path(py).as_posix()):
        text = text.replace(raw, "<PY>")
    for raw in (str(home), home.as_posix()):
        text = text.replace(raw, "<HOME>")
    for raw in (str(CORE), CORE.as_posix()):
        text = text.replace(raw, "<CORE>")
    text = re.sub(r"(<(?:CORE|HOME|PY)>)([^\s`\"']*)", lambda m: m[1] + m[2].replace("\\", "/"), text)
    return re.sub(r"\b[0-9a-f]{64}\b", "<sha>", text)


def _normalize_hooks(text: str, home: Path) -> str:
    def walk(v):
        if isinstance(v, str):
            return re.sub(r"'(<(?:CORE|HOME|PY)>[^'\s]*)'", r"\1", _normalize(v, home))
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    return json.dumps(walk(json.loads(text)), indent=2, sort_keys=True) + "\n"


def render(example: str, base: Path) -> dict[str, str]:
    home = base / "home"
    home.mkdir(parents=True, exist_ok=True)
    ov = load(CORE / "overlay-examples" / example)
    out = {}
    for path, text in install.plan(CORE, ov, home):
        rel = path.relative_to(home).as_posix()
        if _kept(rel):
            out[rel] = _normalize_hooks(text, home) if rel == "hooks.json" else _normalize(text, home).replace("\r\n", "\n")
    skills = base / "skills"
    install.install_skills(install.skill_sources(CORE, ov.root), skills)
    for f in sorted(p for p in skills.rglob("*") if p.is_file()):
        out["skills/" + f.relative_to(skills).as_posix()] = _normalize(f.read_text(encoding="utf-8"), home).replace("\r\n", "\n")
    return out


def _fixture(example: str) -> dict[str, str]:
    root = FIXTURES / example
    return {rename(p.relative_to(root).as_posix()): rename(p.read_text(encoding="utf-8"))
            for p in sorted(root.rglob("*")) if p.is_file()}


def capture() -> None:
    for example in EXAMPLES:
        root = FIXTURES / example
        shutil.rmtree(root, True)
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "dir with space" / "ação"
            base.mkdir(parents=True)
            for rel, text in render(example, base).items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8", newline="\n")


class GoldenTest(unittest.TestCase):
    def test_codex_output_matches_fixtures_apart_from_the_rename(self):
        for example in EXAMPLES:
            with self.subTest(example=example):
                got = render(example, tree(self))
                want = _fixture(example)
                self.assertEqual(sorted(got), sorted(want))
                for rel in want:
                    self.assertEqual(got[rel], want[rel], rel)


if __name__ == "__main__":
    if "--capture" in sys.argv:
        capture()
    else:
        unittest.main()
