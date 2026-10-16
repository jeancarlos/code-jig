import hashlib
import io
import unittest
import zipfile
from unittest import mock

import bootstrap
from harness.install import release_digest
from tests.util import tree, write

TAG = "v1.2.3"


def make_zip(files, tag=TAG, digest=None, extra=()):
    staging = {name: data for name, data in files.items()}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in staging.items():
            zf.writestr(name, data)
        for info, data in extra:
            zf.writestr(info, data)
        if digest is None:
            h = hashlib.sha256()
            for name in sorted(staging):
                h.update(name.encode() + b"\0" + staging[name].encode() + b"\0")
            digest = h.hexdigest()
        zf.writestr("VERSION", f"{tag}\n{digest}\n")
    return buf.getvalue()


FILES = {"harness/__init__.py": "VERSION = '1.2.3'\n", "README.md": "readme\n", "core/AGENTS.core.md": "rules\n"}


class Digest(unittest.TestCase):
    def test_same_as_harness(self):
        root = tree(self)
        write(root / "a-b" / "x", "1")
        write(root / "a" / "b", "2")
        write(root / "VERSION", "ignored")
        write(root / "pkg" / "__pycache__" / "m.pyc", "ignored")
        self.assertEqual(bootstrap.release_digest(root), release_digest(root))


class Names(unittest.TestCase):
    def refused(self, name, data="x"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(name, data)
        with self.assertRaises(bootstrap.Refused):
            bootstrap.check_names(zipfile.ZipFile(buf))

    def test_unsafe_names_refused(self):
        for name in ("../x", "a/../../x", "/etc/x", "a\\..\\x", "C:/x", "a/b:stream", "a//b", "./x",
                     "CON", "a/nul.txt", "a/com1", "a/trailing.", "a/trailing "):
            with self.subTest(name=name):
                self.refused(name)

    def test_case_collision_refused(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("README.md", "a")
            zf.writestr("readme.md", "b")
        with self.assertRaises(bootstrap.Refused):
            bootstrap.check_names(zipfile.ZipFile(buf))

    def test_symlink_entry_refused(self):
        info = zipfile.ZipInfo("link")
        info.external_attr = (0o120777 << 16)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(info, "/etc/passwd")
        with self.assertRaises(bootstrap.Refused):
            bootstrap.check_names(zipfile.ZipFile(buf))

    def test_oversize_refused(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("big", b"\0" * 1024)
        with mock.patch.object(bootstrap, "MAX_TREE", 100), self.assertRaises(bootstrap.Refused):
            bootstrap.check_names(zipfile.ZipFile(buf))

    def test_console_and_dirs_are_fine(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("harness/", "")
            zf.writestr("harness/console.py", "x")
        bootstrap.check_names(zipfile.ZipFile(buf))


class Unpack(unittest.TestCase):
    def setUp(self):
        self.data = tree(self) / "data"
        self.data.mkdir()
        self.target = self.data / TAG

    def test_unpacks_and_verifies(self):
        bootstrap.unpack(make_zip(FILES), self.target, TAG)
        self.assertEqual((self.target / "README.md").read_text(encoding="utf-8"), "readme\n")
        bootstrap.verify_tree(self.target, TAG)
        self.assertEqual([p.name for p in self.data.iterdir()], [TAG])

    def test_wrong_tag_refused_and_cleaned(self):
        with self.assertRaises(bootstrap.Refused):
            bootstrap.unpack(make_zip(FILES, tag="v9.9.9"), self.target, TAG)
        self.assertEqual(list(self.data.iterdir()), [])

    def test_wrong_digest_refused(self):
        with self.assertRaises(bootstrap.Refused):
            bootstrap.unpack(make_zip(FILES, digest="0" * 64), self.target, TAG)
        self.assertFalse(self.target.exists())

    def test_tampered_folder_fails_verify(self):
        bootstrap.unpack(make_zip(FILES), self.target, TAG)
        write(self.target / "README.md", "changed\n")
        with self.assertRaises(bootstrap.Refused):
            bootstrap.verify_tree(self.target, TAG)

    def test_concurrent_winner_accepted_when_valid(self):
        bootstrap.unpack(make_zip(FILES), self.target, TAG)
        bootstrap.unpack(make_zip(FILES), self.target, TAG)
        self.assertEqual([p.name for p in self.data.iterdir()], [TAG])

    def test_concurrent_winner_refused_when_invalid(self):
        bootstrap.unpack(make_zip(FILES), self.target, TAG)
        write(self.target / "README.md", "changed\n")
        with self.assertRaises(bootstrap.Refused):
            bootstrap.unpack(make_zip(FILES), self.target, TAG)
        self.assertEqual([p.name for p in self.data.iterdir()], [TAG])


class Tags(unittest.TestCase):
    def test_grammar(self):
        self.assertEqual(bootstrap.valid_tag("v0.11.0"), "v0.11.0")
        for bad in ("0.11.0", "v0.11", "v0.11.0.evil", "v0.11.0-rc1", "latest", "", None):
            with self.subTest(bad=bad), self.assertRaises(bootstrap.Refused):
                bootstrap.valid_tag(bad)


class Source(unittest.TestCase):
    def test_ascii_and_python38_parseable(self):
        import ast
        src = (bootstrap.Path(bootstrap.__file__)).read_bytes()
        src.decode("ascii")
        ast.parse(src, feature_version=(3, 8))
