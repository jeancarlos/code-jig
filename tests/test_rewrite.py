import contextlib
import http.server
import io
import json
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from codejig import rewrite
from tests.util import tree, write

PY = '''def secret_token_value():
    """This function returns the token value."""
    # Helper function to compute x
    # Step 1: load
    return 1  # trailing note
'''


def reply(blocks):
    return lambda sent: blocks


class Blocks(unittest.TestCase):
    def test_only_comments_and_docstrings_with_a_tell_are_picked(self):
        found = rewrite.flagged(PY, "a.py")
        self.assertEqual([[t for _, t, _ in b] for b in found],
                         [["This function returns the token value."], ["Helper function to compute x", "Step 1: load"]])

    def test_tool_directives_are_never_flagged(self):
        self.assertEqual(rewrite.flagged("# noqa: this function is fine\nx = 1\n# type: ignore\n", "a.py"), [])

    def test_plain_comments_are_not_flagged(self):
        self.assertEqual(rewrite.flagged("# retry twice, the api drops the first call\nx = 1\n", "a.py"), [])

    def test_jsdoc_and_line_comments_are_picked_with_their_markers_kept(self):
        text = "/**\n * This method returns the id.\n * @param a first\n */\nfunction f(a) {}\n// Updated to use a lock\n"
        found = rewrite.flagged(text, "a.ts")
        self.assertEqual([[t for _, t, _ in b] for b in found],
                         [["", "This method returns the id.", "@param a first", ""], ["Updated to use a lock"]])


class Apply(unittest.TestCase):
    def test_new_text_goes_back_between_the_original_markers(self):
        out, n, _ = rewrite.rewrite_text(PY, "a.py", reply([["gets the token"], ["compute x", "load it"]]))
        self.assertEqual(n, 2)
        self.assertEqual(out, PY.replace("This function returns the token value.", "gets the token")
                         .replace("Helper function to compute x", "compute x").replace("Step 1: load", "load it"))

    def test_jsdoc_keeps_stars_and_delimiters(self):
        text = "/**\n * This method returns the id.\n */\nfunction f() {}\n"
        out, n, _ = rewrite.rewrite_text(text, "a.ts", reply([["", "returns the id", ""]]))
        self.assertEqual(out, "/**\n * returns the id\n */\nfunction f() {}\n")

    def test_a_reply_with_the_wrong_shape_changes_nothing(self):
        for bad in ([["one"]], [["a", "b"], ["c", "d", "e"]], "x", None):
            with self.subTest(bad=bad):
                out, n, refused = rewrite.rewrite_text(PY, "a.py", reply(bad))
                self.assertEqual((out, n, refused), (PY, 0, 2))

    def test_unsafe_lines_are_refused_one_block_at_a_time(self):
        zero = chr(0x200B)
        for line in ("it */ ends the comment", 'has """ inside', "two\nlines", f"hidden{zero}char",
                     "Co-authored-by: Codex <x@y.z>", "This function again", "a" * 400, "dash " + chr(0x2014) + " back",
                     "a\rb", "a\x0bb", "a\x0cb", "a" + chr(0x85) + "b", "a" + chr(0x2028) + "b", "tab\there", "ends with \\", "tri ??/", "open /* here", "java \\u000a escape", "a\\nb", "coding: utf-7", "vim: set fileencoding=utf-7"):
            with self.subTest(line=line):
                out, n, refused = rewrite.rewrite_text(PY, "a.py", reply([["fine text"], [line, "ok"]]))
                self.assertEqual((n, refused), (1, 1))
                self.assertIn("fine text", out)
                self.assertIn("Helper function to compute x", out)

    def test_a_reply_that_changes_the_code_around_a_comment_is_dropped_even_if_the_line_checks_pass(self):
        text = "/**\n * This method returns the id.\n */\nfunction f() {}\n"
        with mock.patch.object(rewrite, "SAFE", lambda old, new: True):
            out, n, refused = rewrite.rewrite_text(text, "a.ts", reply([["", "ok */ run(); /* x", ""]]))
        self.assertEqual((out, n, refused), (text, 0, 1))
        py = 'def f():\n    """This function goes."""\n    return 1\n'
        with mock.patch.object(rewrite, "SAFE", lambda old, new: True):
            self.assertEqual(rewrite.rewrite_text(py, "a.py", reply([['go""" ; import os #']])), (py, 0, 1))

    def test_the_exact_bytes_are_parsed_and_a_source_encoding_line_is_never_flagged(self):
        py = "# coding: latin-1\n# Step 1: go\nx = 1\n"
        self.assertEqual(rewrite.flagged(py, "a.py"), [])
        self.assertEqual(rewrite.flagged("#!/usr/bin/env python\n# fileencoding=utf-8 helper function\nx = 1\n", "a.py"), [])

    def test_rust_block_comments_nest(self):
        text = "/**\n * This function uses /* nested */ text.\n */\nfn f() {}\n"
        self.assertEqual(len(rewrite.flagged(text, "a.rs")), 1)
        with mock.patch.object(rewrite, "SAFE", lambda old, new: True):
            self.assertEqual(rewrite.rewrite_text(text, "a.rs", reply([["", "ok /* open", ""]])), (text, 0, 1))

    def test_js_files_with_a_regex_literal_are_not_rewritten(self):
        with_regex = '/** This method strips quotes. */\nconst q = /"/g;\n'
        division = '/** This method halves it. */\nconst h = total / 2;\n'
        yielded = '/** This method halves it. */\nfunction* g() { yield /"/; }\n'
        plain = '/** This method halves it. */\nconst h = total;\n'
        for text in (with_regex, division, yielded):
            self.assertEqual(rewrite.flagged(text, "a.js"), [])
        self.assertEqual(len(rewrite.flagged(plain, "a.js")), 1)

    def test_a_python_result_that_does_not_parse_is_dropped(self):
        with mock.patch.object(rewrite, "SAFE", lambda old, new: True):
            out, n, refused = rewrite.rewrite_text(PY, "a.py", reply([['x"""y'], ["ok", "ok"]]))
            self.assertEqual((out, n, refused), (PY, 0, 2))


class Settings(unittest.TestCase):
    def test_url_comes_from_the_flag_then_the_rewrite_variable_then_the_gateway_variable(self):
        env = {"NINEROUTER_URL": "http://gw:1/", "CODEJIG_REWRITE_URL": "http://own:2/v1"}
        with mock.patch.dict("os.environ", env, clear=True):
            self.assertEqual(rewrite.gateway_url("http://flag/v1"), "http://flag/v1")
            self.assertEqual(rewrite.gateway_url(None), "http://own:2/v1")
        with mock.patch.dict("os.environ", {"NINEROUTER_URL": "http://gw:1/"}, clear=True):
            self.assertEqual(rewrite.gateway_url(None), "http://gw:1/v1")
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(rewrite.gateway_url(None), rewrite.DEFAULT_URL)

    def test_key_comes_from_the_variables_then_the_key_file(self):
        home = tree(self)
        write(home / ".config" / "9router.key", "file-key\n")
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch("pathlib.Path.home", return_value=home):
            self.assertEqual(rewrite.gateway_key(), "file-key")
            with mock.patch.dict("os.environ", {"NINEROUTER_KEY": "env-key"}):
                self.assertEqual(rewrite.gateway_key(), "env-key")
            with mock.patch.dict("os.environ", {"NINEROUTER_KEY": "env-key", "CODEJIG_REWRITE_KEY": "own-key"}):
                self.assertEqual(rewrite.gateway_key(), "own-key")
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch("pathlib.Path.home", return_value=tree(self)):
            self.assertIsNone(rewrite.gateway_key())


class Gateway(unittest.TestCase):
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            Gateway.seen.append((self.path, body))
            sent = json.loads(body["messages"][-1]["content"])["blocks"]
            answer = {"blocks": [[t.replace("This function returns", "gets") for t in b] for b in sent]}
            payload = json.dumps({"choices": [{"message": {"content": "```json\n" + json.dumps(answer) + "\n```"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), cls.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        Gateway.seen.clear()
        self.root = tree(self)
        self.enterContext(contextlib.chdir(self.root))

    def args(self, **kw):
        base = dict(path=[str(self.root)], rewrite=True, check=False, yes=True, model="m-test", persona=None, url=self.url)
        return SimpleNamespace(**{**base, **kw})

    def test_only_comment_text_is_sent_and_the_file_is_rewritten(self):
        path = write(self.root / "a.py", PY)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(rewrite.run(self.args()), 0)
        [(route, body)] = Gateway.seen
        self.assertEqual((route, body["model"], body["stream"]), ("/v1/chat/completions", "m-test", False))
        wire = json.dumps(body)
        self.assertNotIn("secret_token_value", wire)
        self.assertNotIn("return 1", wire)
        self.assertIn("This function returns the token value.", wire)
        self.assertIn(rewrite.PERSONA[:40], body["messages"][0]["content"])
        self.assertIn('"""gets the token value."""', path.read_text(encoding="utf-8"))

    def test_the_summary_line_counts_refused_blocks(self):
        write(self.root / "a.py", PY)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rewrite.run(self.args())
        self.assertIn("a.py: 1 of the flagged blocks rewritten, 1 refused", err.getvalue())

    def test_without_yes_a_non_interactive_run_sends_nothing(self):
        write(self.root / "a.py", PY)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch("sys.stdin.isatty", return_value=False):
            self.assertEqual(rewrite.run(self.args(yes=False)), 2)
        self.assertEqual(Gateway.seen, [])
        self.assertIn("--yes", err.getvalue())

    def test_check_lists_what_would_be_sent_and_sends_nothing(self):
        path = write(self.root / "a.py", PY)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(rewrite.run(self.args(check=True, yes=False)), 0)
        self.assertEqual(Gateway.seen, [])
        self.assertEqual(path.read_text(encoding="utf-8"), PY)
        self.assertIn("a.py", err.getvalue())

    def test_a_file_with_nothing_flagged_sends_nothing(self):
        write(self.root / "a.py", "# retry twice, the api drops the first call\nx = 1\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(rewrite.run(self.args()), 0)
        self.assertEqual(Gateway.seen, [])

    def test_plain_http_is_only_allowed_to_this_machine(self):
        for url in ("http://example.com/v1", "http://192.168.1.5:20128/v1", "ftp://x/v1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                rewrite.gateway(url, "m", "p", "k")
        for url in ("http://127.0.0.1:1/v1", "http://localhost/v1", "http://[::1]:5/v1", "https://example.com/v1"):
            with self.subTest(url=url):
                rewrite.gateway(url, "m", "p", "k")

    def test_a_redirect_is_never_followed_so_the_key_stays_put(self):
        class Elsewhere(http.server.BaseHTTPRequestHandler):
            got = []

            def do_GET(self):
                Elsewhere.got.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        other = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Elsewhere)
        threading.Thread(target=other.serve_forever, daemon=True).start()
        self.addCleanup(other.shutdown)

        class Bounce(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{other.server_address[1]}/steal")
                self.end_headers()

            def log_message(self, *args):
                pass

        bounce = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Bounce)
        threading.Thread(target=bounce.serve_forever, daemon=True).start()
        self.addCleanup(bounce.shutdown)
        ask = rewrite.gateway(f"http://127.0.0.1:{bounce.server_address[1]}/v1", "m", "p", "secret-key")
        with self.assertRaises(OSError):
            ask([["x"]])
        self.assertEqual(Elsewhere.got, [])

    def test_only_http_gateways_are_accepted(self):
        path = write(self.root / "a.py", PY)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(rewrite.run(self.args(url="file:///etc/passwd")), 1)
        self.assertEqual(path.read_text(encoding="utf-8"), PY)
        self.assertIn("http", err.getvalue())

    def test_a_gateway_that_is_down_leaves_the_file_alone(self):
        path = write(self.root / "a.py", PY)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(rewrite.run(self.args(url="http://127.0.0.1:1/v1")), 1)
        self.assertEqual(path.read_text(encoding="utf-8"), PY)
