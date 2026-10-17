import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import bootstrap
from codejig import VERSION
from codejig.install import release_digest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github" / "scripts" / "build_release.py"
TAG = f"v{VERSION}"
TOP = {"codejig", "core", "skills", "overlay-examples", "bench", "install.sh", "install.ps1", "bootstrap.py",
       "LICENSE", "README.md", "VERSION"}
REQUIRED = {"VERSION", "bench/requirements.toml", "codejig/__main__.py", "core/AGENTS.core.md", "core/tiers.toml",
            "overlay-examples/release/overlay.toml", "overlay-examples/release/profiles.toml", "install.sh",
            "install.ps1", "bootstrap.py", "LICENSE", "README.md"}


def build(tag, out):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run([sys.executable, str(SCRIPT), tag, str(out)], env=env, capture_output=True, text=True,
                          encoding="utf-8", check=False)


@unittest.skipUnless((ROOT / ".git").exists(), "needs a git checkout")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        done = build(TAG, cls.tmp / "a")
        assert done.returncode == 0, done.stderr
        cls.zip = (cls.tmp / "a" / "code-jig.zip").read_bytes()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def names(self):
        return zipfile.ZipFile(self.tmp / "a" / "code-jig.zip").namelist()

    def test_contents(self):
        files = {n for n in self.names() if not n.endswith("/")}
        self.assertLessEqual({n.split("/")[0] for n in files}, TOP)
        self.assertLessEqual(REQUIRED, files)
        self.assertEqual({n for n in files if n.startswith("bench/")}, {"bench/requirements.toml"})
        for n in files:
            with self.subTest(n=n):
                self.assertNotIn("/evals/", f"/{n}")
                self.assertFalse(n.endswith(("evals.toml", ".skill-check")))
                self.assertNotIn("__pycache__", n)

    def test_version_digest(self):
        out = self.tmp / "x"
        zipfile.ZipFile(self.tmp / "a" / "code-jig.zip").extractall(out)
        self.assertEqual((out / "VERSION").read_text(encoding="utf-8").split(), [TAG, release_digest(out)])
        bootstrap.verify_tree(out, TAG)

    def test_sums_and_bootstrap(self):
        sums = (self.tmp / "a" / "SHA256SUMS").read_text(encoding="utf-8")
        self.assertEqual(sums, f"{hashlib.sha256(self.zip).hexdigest()}  code-jig.zip\n")
        self.assertEqual((self.tmp / "a" / "bootstrap.py").read_bytes(), (ROOT / "bootstrap.py").read_bytes())

    def test_reproducible(self):
        self.assertEqual(build(TAG, self.tmp / "b").returncode, 0)
        self.assertEqual((self.tmp / "b" / "code-jig.zip").read_bytes(), self.zip)

    def test_bootstrap_accepts_the_archive(self):
        bootstrap.check_names(zipfile.ZipFile(self.tmp / "a" / "code-jig.zip"))

    def test_tag_must_match_version(self):
        for tag in ("v9.9.9", "nightly", f"{TAG}.1"):
            with self.subTest(tag=tag):
                done = build(tag, self.tmp / "c")
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("does not match", done.stderr)


def _readme_install():
    import importlib.util
    spec = importlib.util.spec_from_file_location("readme_install", ROOT / ".github" / "scripts" / "readme_install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ReadmeInstall(unittest.TestCase):
    mod = _readme_install()

    def blocks(self, text, lang):
        return [b.strip() for b in __import__("re").findall(rf"```{lang}\n(.*?)```", text, flags=__import__("re").S)]

    def test_commands_paste_without_edits(self):
        block = self.mod.render("v1.2.3")
        commands = self.blocks(block, "sh") + self.blocks(block, "powershell")
        self.assertEqual(len(commands), 3)
        for cmd in commands:
            with self.subTest(cmd=cmd):
                self.assertNotRegex(cmd, r"[<>]")
                self.assertIn("/releases/download/v1.2.3/bootstrap.py", cmd)
        shells = [s for s in ("bash", "zsh") if shutil.which(s)]
        for shell in shells:
            for cmd in self.blocks(block, "sh"):
                with self.subTest(shell=shell, cmd=cmd):
                    self.assertEqual(subprocess.run([shell, "-n", "-c", cmd], check=False).returncode, 0)

    def test_update_is_idempotent_and_keeps_the_rest(self):
        text = f"top\n{self.mod.START}\nold\n{self.mod.END}\nbottom\n"
        once = self.mod.update(text, "v1.2.3")
        self.assertEqual(self.mod.update(once, "v1.2.3"), once)
        self.assertTrue(once.startswith("top\n") and once.endswith("\nbottom\n"))
        with self.assertRaises(ValueError):
            self.mod.render("latest")
        with self.assertRaises(ValueError):
            self.mod.update("no block", "v1.2.3")

    def test_readme_block_is_the_rendered_one(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        tag = __import__("re").search(r"Latest release: \*\*(v\d+\.\d+\.\d+)\*\*", text)[1]
        self.assertEqual(self.mod.update(text, tag), text)
