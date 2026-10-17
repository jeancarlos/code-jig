from codejig import evidence, gitgate, humanize, sources, trace

EXPECTED = (ValueError, KeyError, IndexError, LookupError)


def undash(data: bytes) -> None:
    try:
        gitgate.undash(data)
    except UnicodeDecodeError:
        pass


def read_ids(data: bytes) -> None:
    try:
        trace.read_ids(data.decode("utf-8", "replace"))
    except ValueError:
        pass


def page_text(data: bytes) -> None:
    sources.page_text(data, "text/html; charset=utf-8")
    sources.page_text(data, "text/plain")


def humanize_text(data: bytes) -> None:
    humanize.humanize_text(data.decode("utf-8", "replace"), "#")


def parse_log(data: bytes) -> None:
    try:
        evidence.parse_log(data.decode("utf-8", "replace"))
    except EXPECTED:
        pass


TARGETS = [undash, read_ids, page_text, humanize_text, parse_log]
