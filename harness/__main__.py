from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="harness")
    p.add_argument("--overlay")
    p.add_argument("--codex-home")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("install")
    d = sub.add_parser("doctor")
    d.add_argument("--codex-bin")
    d.add_argument("--check-binary", action="store_true")
    d.add_argument("--live", action="store_true")
    c = sub.add_parser("collect")
    c.add_argument("--rescan", action="store_true")
    h = sub.add_parser("hooks")
    h.add_argument("--hook-type", choices=["claude-code", "codex"], required=True)
    h.add_argument("path", nargs="*")
    hu = sub.add_parser("humanize")
    hu.add_argument("path", nargs="*")
    hu.add_argument("--check", action="store_true", help="dry-run: report changes without writing")
    t = sub.add_parser("tokens")
    t.add_argument("--days", type=int, default=7)
    t.add_argument("--cache-floor", type=float, default=97.5)
    t.add_argument("--top", type=int, default=10)
    r = sub.add_parser("cross-review")
    r.add_argument("--base")
    r.add_argument("--profile", default="review")
    r.add_argument("--codex-bin")
    r.add_argument("files", nargs="*")
    a = sub.add_parser("analyze")
    a.add_argument("path", nargs="?", default=".")
    a.add_argument("--base")
    a.add_argument("--top", type=int, default=10)
    a.add_argument("--json", action="store_true")
    a.add_argument("--timeout", type=int, default=600)
    tr = sub.add_parser("trace")
    tr.add_argument("ids")
    tr.add_argument("--path", default=".")
    tr.add_argument("--pattern", default="REQ-{id}")
    tr.add_argument("--json", action="store_true")
    ev = sub.add_parser("evidence")
    ev.add_argument("--days", type=int, default=90)
    ev.add_argument("--repo")
    ev.add_argument("--analyze", type=int, default=0)
    ev.add_argument("--timeout", type=int, default=600)
    ev.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("harness: Python 3.11 or newer is required", file=sys.stderr)
        return 2
    args = build_parser().parse_args(argv)
    if args.cmd == "install":
        from harness.install import cli
    elif args.cmd == "collect":
        from harness.collect import cli
    elif args.cmd == "tokens":
        from harness.tokens import cli
    elif args.cmd == "cross-review":
        from harness.review import cli
    elif args.cmd == "analyze":
        from harness.analyze import cli
    elif args.cmd == "trace":
        from harness.trace import cli
    elif args.cmd == "evidence":
        from harness.evidence import cli
    elif args.cmd == "hooks":
        from harness.hooks import cli
    elif args.cmd == "humanize":
        from harness.humanize import cli
    else:
        from harness.doctor import cli
    return cli(args)


if __name__ == "__main__":
    sys.exit(main())
