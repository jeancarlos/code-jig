import hashlib
import io
import unittest
import urllib.error
from email.message import Message
from unittest import mock

import bootstrap
from tests.test_bootstrap_unpack import FILES, TAG, make_zip
from tests.util import tree, write


def http_error(url, code, location=None):
    headers = Message()
    if location:
        headers["Location"] = location
    return urllib.error.HTTPError(url, code, "x", headers, io.BytesIO(b""))


class Allowed(unittest.TestCase):
    def test_schemes(self):
        self.assertTrue(bootstrap.allowed("https://code-jig.jeansouza.dev/x"))
        self.assertTrue(bootstrap.allowed("http://127.0.0.1:8765/x"))
        self.assertTrue(bootstrap.allowed("http://localhost/x"))
        for url in ("http://example.com/x", "file:///etc/passwd", "ftp://h/x", "http://127.0.0.1.evil.com/x"):
            with self.subTest(url=url):
                self.assertFalse(bootstrap.allowed(url))

    def test_fetch_refuses_plain_http(self):
        with self.assertRaises(bootstrap.Refused):
            bootstrap.fetch("http://example.com/x", 10)

    def test_redirect_to_http_refused(self):
        handler = bootstrap.Redirects()
        with self.assertRaises(bootstrap.Refused):
            handler.redirect_request(mock.Mock(), None, 302, "Found", {}, "http://example.com/x")


class Fallback(unittest.TestCase):
    def run_with(self, *effects):
        calls = []

        def fake(url, limit):
            calls.append(url)
            effect = effects[len(calls) - 1]
            if isinstance(effect, BaseException):
                raise effect
            return effect

        with mock.patch.object(bootstrap, "fetch", side_effect=fake):
            result = bootstrap.fetch_asset(TAG, "SHA256SUMS", "https://w.example", "o/r", 100)
        return result, calls

    def test_primary_ok(self):
        result, calls = self.run_with(b"sums")
        self.assertEqual((result, calls), (b"sums", [f"https://w.example/v/{TAG}/SHA256SUMS"]))

    def test_connection_error_falls_back(self):
        result, calls = self.run_with(urllib.error.URLError("refused"), b"sums")
        self.assertEqual(result, b"sums")
        self.assertEqual(calls[1], f"https://github.com/o/r/releases/download/{TAG}/SHA256SUMS")

    def test_timeout_and_5xx_fall_back(self):
        for err in (TimeoutError("slow"), http_error("u", 503)):
            with self.subTest(err=err):
                self.assertEqual(self.run_with(err, b"ok")[0], b"ok")

    def test_404_stops_with_no_zip_message(self):
        with self.assertRaisesRegex(bootstrap.Refused, "before v0.11.0"):
            self.run_with(http_error("u", 404))

    def test_403_stops(self):
        with self.assertRaises(bootstrap.Refused):
            self.run_with(http_error("u", 403))

    def test_refused_redirect_never_falls_back(self):
        with self.assertRaises(bootstrap.Refused):
            self.run_with(bootstrap.Refused("redirect"), b"never")


class Latest(unittest.TestCase):
    def opener(self, effect):
        op = mock.Mock()
        op.open.side_effect = effect
        return mock.patch.object(bootstrap.urllib.request, "build_opener", return_value=op)

    def test_resolves_from_location(self):
        err = http_error("u", 302, "https://github.com/o/r/releases/tag/v0.11.2")
        with self.opener(err):
            self.assertEqual(bootstrap.resolve_latest("o/r"), "v0.11.2")

    def test_bad_tag_in_location_refused(self):
        err = http_error("u", 302, "https://github.com/o/r/releases/tag/nightly")
        with self.opener(err), self.assertRaises(bootstrap.Refused):
            bootstrap.resolve_latest("o/r")

    def test_no_release_refused(self):
        with self.opener(http_error("u", 404)), self.assertRaises(bootstrap.Refused):
            bootstrap.resolve_latest("o/r")


class Sums(unittest.TestCase):
    def test_parse(self):
        digest = "a" * 64
        self.assertEqual(bootstrap.parse_sums(f"{digest}  code-jig.zip\n".encode()), digest)
        self.assertEqual(bootstrap.parse_sums(f"{digest} *code-jig.zip\n".encode()), digest)
        with self.assertRaises(bootstrap.Refused):
            bootstrap.parse_sums(f"{digest}  other.zip\n".encode())


class GetCore(unittest.TestCase):
    def setUp(self):
        self.data = tree(self) / "data"
        self.blob = make_zip(FILES)
        self.sums = f"{hashlib.sha256(self.blob).hexdigest()}  code-jig.zip\n".encode()

    def serve(self, sums, blob):
        return mock.patch.object(bootstrap, "fetch_asset", side_effect=lambda tag, name, *a: sums if name == "SHA256SUMS" else blob)

    def test_downloads_then_reuses(self):
        with self.serve(self.sums, self.blob) as fa:
            core = bootstrap.get_core(TAG, self.data, "https://w", "o/r")
            self.assertEqual(core, self.data / TAG)
            bootstrap.get_core(TAG, self.data, "https://w", "o/r")
        self.assertEqual(fa.call_count, 2)

    def test_checksum_mismatch_refused(self):
        with self.serve(("0" * 64 + "  code-jig.zip\n").encode(), self.blob), self.assertRaises(bootstrap.Refused):
            bootstrap.get_core(TAG, self.data, "https://w", "o/r")
        self.assertFalse((self.data / TAG).exists())

    def test_tampered_reuse_refused(self):
        with self.serve(self.sums, self.blob):
            bootstrap.get_core(TAG, self.data, "https://w", "o/r")
        write(self.data / TAG / "README.md", "evil\n")
        with self.serve(self.sums, self.blob), self.assertRaisesRegex(bootstrap.Refused, "delete it and rerun"):
            bootstrap.get_core(TAG, self.data, "https://w", "o/r")
