import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from codejig import VERSION, paths
from codejig.install import release_digest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
import build_wheel

TAG = f"v{VERSION}"


@unittest.skipUnless((ROOT / ".git").exists(), "needs a git checkout")
class Stage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        build_wheel.stage(TAG, cls.tmp)
        cls.core = cls.tmp / "codejig" / "_core"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def test_data_sits_inside_the_package(self):
        self.assertEqual({p.name for p in self.core.iterdir()}, {"core", "skills", "bench", "VERSION"})
        self.assertEqual([p.name for p in (self.core / "bench").iterdir()], ["requirements.toml"])
        self.assertTrue((self.tmp / "pyproject.toml").is_file())
        self.assertFalse((self.tmp / "core").exists())

    def test_version_names_the_tag_and_the_data_digest(self):
        tag, digest = (self.core / "VERSION").read_text(encoding="utf-8").split()
        self.assertEqual((tag, digest), (TAG, release_digest(self.core)))

    def test_no_eval_fixtures_ship(self):
        names = [p.relative_to(self.core).as_posix() for p in self.core.rglob("*") if p.is_file()]
        self.assertFalse([n for n in names if "/evals/" in f"/{n}" or n.endswith(("evals.toml", ".skill-check"))])

    def test_a_wrong_tag_is_refused(self):
        with self.assertRaises(SystemExit):
            build_wheel.build("v9.9.9", self.tmp / "out")


class CoreLocation(unittest.TestCase):
    def test_core_is_the_packaged_data_when_it_exists(self):
        with tempfile.TemporaryDirectory() as d:
            code = Path(d) / "codejig"
            (code / "_core").mkdir(parents=True)
            self.assertEqual(paths.locate_core(code), code / "_core")

    def test_core_is_the_checkout_without_packaged_data(self):
        self.assertEqual(paths.locate_core(paths.CODE), ROOT)
        self.assertEqual(paths.CORE, ROOT)
