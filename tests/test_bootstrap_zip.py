import contextlib
import hashlib
import io
import os
import unittest
from unittest import mock

import bootstrap
from tests.test_bootstrap_unpack import FILES, TAG, make_zip
from tests.util import tree, write


class ZipInstall(unittest.TestCase):
    def setUp(self):
        self.root = tree(self)
        self.zip = self.root / "dl" / "code-jig.zip"
        self.blob = make_zip(FILES)
        self.zip.parent.mkdir()
        self.zip.write_bytes(self.blob)
        self.overlay = self.root / "overlay"
        self.pin(TAG)
        self.err = io.StringIO()

    def pin(self, tag):
        write(self.overlay / "overlay.toml", f'core_version = "{tag}"\ncore_writable = false\n')

    def sums(self, digest=None):
        digest = digest or hashlib.sha256(self.blob).hexdigest()
        write(self.zip.parent / "SHA256SUMS", f"{digest}  code-jig.zip\n")

    def go(self, *extra):
        argv = ["--zip", str(self.zip), "--overlay", str(self.overlay), "--data-dir", str(self.root / "data"),
                "--bin-dir", str(self.root / "bin"), *extra]
        with mock.patch.object(bootstrap, "fetch", side_effect=AssertionError("network")), \
                mock.patch.object(bootstrap, "run_install", return_value=0) as inst, \
                mock.patch.object(bootstrap, "run_doctor"), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(self.err):
            rc = bootstrap.run(bootstrap.parse_args(argv))
        return rc, inst

    def test_zip_install_needs_no_network(self):
        self.sums()
        rc, inst = self.go()
        self.assertEqual(rc, 0)
        bootstrap.verify_tree(self.root / "data" / TAG, TAG)
        self.assertTrue(all(p.exists() for p in bootstrap.launcher_paths(self.root / "bin")))
        self.assertTrue(inst.called)

    def test_zip_with_bad_sums_is_refused(self):
        self.sums("0" * 64)
        with self.assertRaisesRegex(bootstrap.Refused, "does not match"):
            self.go()
        self.assertFalse((self.root / "data" / TAG).exists())

    def test_zip_without_sums_warns(self):
        rc, _ = self.go()
        self.assertEqual(rc, 0)
        self.assertIn(f"warning: no SHA256SUMS next to {self.zip}; not verified", self.err.getvalue())

    def test_older_zip_needs_explicit_version(self):
        self.pin("v9.0.0")
        write(self.overlay / "overlay.toml", '# written by code-jig bootstrap\ncore_version = "v9.0.0"\ncore_writable = false\n')
        with self.assertRaisesRegex(bootstrap.Refused, "older"):
            self.go()
        rc, _ = self.go("--version", TAG)
        self.assertEqual(rc, 0)
        self.assertEqual(bootstrap.read_pin(self.overlay), TAG)

    def test_version_must_match_the_zip(self):
        with self.assertRaises(bootstrap.Refused):
            self.go("--version", "v9.9.9")

    def test_downloads_from_github_by_default(self):
        urls = []

        def fake(url, limit):
            urls.append(url)
            return self.blob if url.endswith(".zip") else f"{hashlib.sha256(self.blob).hexdigest()}  code-jig.zip\n".encode()

        argv = ["--version", TAG, "--overlay", str(self.overlay), "--data-dir", str(self.root / "data"),
                "--bin-dir", str(self.root / "bin")]
        with mock.patch.object(bootstrap, "fetch", side_effect=fake), \
                mock.patch.object(bootstrap, "run_install", return_value=0), mock.patch.object(bootstrap, "run_doctor"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap.run(bootstrap.parse_args(argv)), 0)
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls, [f"https://github.com/jeancarlos/code-jig/releases/download/{TAG}/{n}" for n in ("SHA256SUMS", "code-jig.zip")])


class LauncherPath(unittest.TestCase):
    def test_launchers_export_their_path(self):
        sh = bootstrap.sh_launcher("py", "/c", "/o", "v1.2.3")
        self.assertIn('CODE_JIG_LAUNCHER="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"', sh)
        self.assertIn("export PYTHONPATH CODE_JIG_OVERLAY CODE_JIG_LAUNCHER", sh)
        cmd = bootstrap.cmd_launcher("py", "C:\\c", "C:\\o", "v1.2.3")
        self.assertIn('set "CODE_JIG_LAUNCHER=%~f0"', cmd)

    @unittest.skipIf(os.name == "nt", "sh launcher")
    def test_sh_launcher_resolves_a_relative_invocation(self):
        import subprocess
        root = tree(self)
        path = root / "bin" / "code-jig"
        write(path, bootstrap.sh_launcher("/bin/sh", "/c", "/o", "v1.2.3").replace(
            'exec /bin/sh -P -s -m codejig "$@"', 'echo "$CODE_JIG_LAUNCHER"'))
        done = subprocess.run(["sh", "./code-jig"], cwd=root / "bin", capture_output=True, text=True, check=False)
        self.assertEqual(done.stdout.strip(), os.path.realpath(path))
