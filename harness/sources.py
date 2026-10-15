import ipaddress
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

MAX_BYTES = 3_000_000
TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; codex-harness check-sources)"
BLOCKED = {401, 403, 429, 451}
SKIP_TAGS = {"script", "style", "noscript", "template"}
TEXT_TYPES = ("text/", "application/xhtml", "application/xml", "application/json")
FOLD = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
                      "\u00a0": " ", "\u202f": " "})
FAILING = {"dead", "quote-missing", "bad-url", "no-quote", "malformed"}


@dataclass
class Claim:
    where: str
    claim: str = ""
    url: str = ""
    quote: str = ""
    verdict: str = ""
    detail: str = ""


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, _attrs):
        self.skip += tag in SKIP_TAGS
        self.parts.append(" ")

    def handle_endtag(self, tag):
        self.skip -= tag in SKIP_TAGS and self.skip > 0
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def normalize(text: str) -> str:
    return " ".join(text.translate(FOLD).casefold().split())


def page_text(body: bytes, ctype: str) -> str:
    charset = re.search(r"charset=([\w-]+)", ctype)
    text = body.decode(charset.group(1) if charset else "utf-8", errors="replace")
    if "html" in ctype or "xml" in ctype:
        parser = _Text()
        parser.feed(text)
        text = "".join(parser.parts)
    return normalize(text)


def is_public(host: str) -> bool:
    """True when every address the host resolves to is a public one; a host that does not resolve passes,
    so the request itself reports it."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return True
    return all(ipaddress.ip_address(info[4][0].split("%")[0]).is_global for info in infos)


def refused(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return "only http and https are checked"
    if not is_public(parts.hostname):
        return f"{parts.hostname} is a private or local address"
    return None


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        reason = refused(newurl)
        if reason:
            raise urllib.error.URLError(f"redirect refused: {reason}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(_Redirects)


def fetch(url: str) -> tuple[str, str]:
    """(verdict, page text or detail) for one URL. Only public http and https addresses are requested,
    redirects included."""
    reason = refused(url)
    if reason:
        return "bad-url", reason
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5"})
    try:
        with OPENER.open(req, timeout=TIMEOUT) as r:
            ctype = r.headers.get("Content-Type", "")
            if not ctype.startswith(TEXT_TYPES):
                return "unreadable", ctype or "unknown type"
            return "ok", page_text(r.read(MAX_BYTES), ctype)
    except urllib.error.HTTPError as e:
        e.close()
        return ("blocked" if e.code in BLOCKED else "dead"), f"HTTP {e.code}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return "dead", str(getattr(e, "reason", e))


def load(files: list[str]) -> list[Claim]:
    claims = []
    for name in files:
        with open(name, encoding="utf-8-sig") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                c = Claim(f"{name}:{n}")
                try:
                    row = json.loads(line)
                    c.claim, c.url, c.quote = (str(row.get(k) or "").strip() for k in ("claim", "url", "quote"))
                except (ValueError, AttributeError):
                    c.verdict, c.detail = "malformed", "not a JSON object"
                    claims.append(c)
                    continue
                if not c.url:
                    c.verdict, c.detail = "malformed", "no url"
                elif not c.url.lower().startswith(("http://", "https://")):
                    c.verdict, c.detail = "bad-url", "only http and https are checked"
                elif not c.quote:
                    c.verdict, c.detail = "no-quote", "a claim needs an exact quote"
                claims.append(c)
    return claims


def check(claims: list[Claim]) -> list[Claim]:
    todo = [c for c in claims if not c.verdict]
    urls = list(dict.fromkeys(c.url for c in todo))
    with ThreadPoolExecutor(max_workers=8) as pool:
        pages = dict(zip(urls, pool.map(fetch, urls), strict=True))
    for c in todo:
        verdict, text = pages[c.url]
        if verdict != "ok":
            c.verdict, c.detail = verdict, text
        elif normalize(c.quote) in text:
            c.verdict = "ok"
        else:
            c.verdict, c.detail = "quote-missing", "the page does not contain the quote"
    return claims


def cli(args) -> int:
    if os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1":
        print("harness: network is disabled in this sandbox; run check-sources with escalation", file=sys.stderr)
        return 2
    try:
        claims = check(load(args.files))
    except OSError as e:
        print(f"harness: {e}", file=sys.stderr)
        return 2
    counts: dict[str, int] = {}
    for c in claims:
        counts[c.verdict] = counts.get(c.verdict, 0) + 1
        note = f" ({c.detail})" if c.detail else ""
        print(f"{c.verdict:13} {c.where}  {c.claim[:70]}  {c.url}{note}")
    print(f"{len(claims)} claims: " + ", ".join(f"{n} {v}" for v, n in sorted(counts.items(), key=lambda kv: kv[0] != "ok")))
    return 1 if FAILING & counts.keys() else 0
