import contextlib
import http.server
import io
import json
import os
import threading
import types
import unittest
from unittest import mock

from harness import sources
from tests.util import tree, write

PAGES = {
    "/doc": (200, "text/html; charset=utf-8",
             ("<html><head><script>var hidden = 'not text';</script><style>p{}</style></head>"
              "<body><p>The default limit is <b>32&nbsp;KiB</b> and Codex \u201cstops adding\u201d files.</p></body></html>")),
    "/plain": (200, "text/plain", "line one\nline   two"),
    "/blocked": (403, "text/html", "no"),
    "/gone": (404, "text/html", "missing"),
    "/pdf": (200, "application/pdf", "%PDF-1.7"),
    "/moved": (301, "text/html", ""),
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        status, ctype, body = PAGES.get(self.path, (404, "text/plain", ""))
        self.send_response(status)
        if status == 301:
            self.send_header("Location", "/doc")
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args):
        pass


class Sources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def evidence(self, rows: list[dict]) -> str:
        return str(write(tree(self) / "evidence.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n"))

    def run_cli(self, *files: str) -> tuple[int, str]:
        out = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "CODEX_SANDBOX_NETWORK_DISABLED"}
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = sources.cli(types.SimpleNamespace(files=list(files)))
        return code, out.getvalue()

    def verdicts(self, rows: list[dict]) -> list[str]:
        claims = sources.load([self.evidence(rows)])
        return [c.verdict for c in sources.check(claims)]

    def test_quote_found_through_markup_entities_and_curly_quotes(self):
        rows = [{"claim": "c", "url": f"{self.base}/doc", "quote": 'default limit is 32 KiB and Codex "stops adding" files'}]
        self.assertEqual(self.verdicts(rows), ["ok"])

    def test_script_text_is_not_page_text(self):
        self.assertEqual(self.verdicts([{"claim": "c", "url": f"{self.base}/doc", "quote": "not text"}]), ["quote-missing"])

    def test_every_outcome(self):
        rows = [
            {"claim": "a", "url": f"{self.base}/plain", "quote": "line one line two"},
            {"claim": "b", "url": f"{self.base}/blocked", "quote": "x"},
            {"claim": "c", "url": f"{self.base}/gone", "quote": "x"},
            {"claim": "d", "url": f"{self.base}/pdf", "quote": "x"},
            {"claim": "e", "url": f"{self.base}/moved", "quote": "default limit"},
            {"claim": "f", "url": "file:///etc/passwd", "quote": "root"},
            {"claim": "g", "url": f"{self.base}/doc"},
        ]
        self.assertEqual(self.verdicts(rows), ["ok", "blocked", "dead", "unreadable", "ok", "bad-url", "no-quote"])

    def test_each_url_is_fetched_once(self):
        rows = [{"claim": str(i), "url": f"{self.base}/doc", "quote": "default limit"} for i in range(5)]
        with mock.patch.object(sources, "fetch", wraps=sources.fetch) as fetch:
            sources.check(sources.load([self.evidence(rows)]))
        self.assertEqual(fetch.call_count, 1)

    def test_cli_exit_codes_and_summary(self):
        good = self.evidence([{"claim": "c", "url": f"{self.base}/doc", "quote": "default limit"}])
        self.assertEqual(self.run_cli(good)[0], 0)
        bad = self.evidence([{"claim": "c", "url": f"{self.base}/gone", "quote": "x"}])
        code, out = self.run_cli(good, bad)
        self.assertEqual(code, 1)
        self.assertIn("2 claims: 1 ok", out)

    def test_malformed_lines_are_reported_not_fatal(self):
        path = write(tree(self) / "e.jsonl", '{"claim": "c", "url": "u"\nnot json\n\n')
        claims = sources.load([str(path)])
        self.assertEqual([c.verdict for c in claims], ["malformed", "malformed"])
        self.assertIn("e.jsonl:2", claims[1].where)

    def test_sandboxed_network_stops_early(self):
        with mock.patch.dict(os.environ, {"CODEX_SANDBOX_NETWORK_DISABLED": "1"}):
            out = io.StringIO()
            with contextlib.redirect_stderr(out):
                code = sources.cli(types.SimpleNamespace(files=[self.evidence([{"claim": "c", "url": "https://x", "quote": "q"}])]))
        self.assertEqual(code, 2)
        self.assertIn("network", out.getvalue())


if __name__ == "__main__":
    unittest.main()
