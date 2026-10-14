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
    t = sub.add_parser("tokens")
    t.add_argument("--days", type=int, default=7)
    t.add_argument("--cache-floor", type=float, default=97.5)
    t.add_argument("--top", type=int, default=10)
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
    else:
        from harness.doctor import cli
    return cli(args)


if __name__ == "__main__":
    sys.exit(main())
