# Contributing

- Python 3.11+, stdlib only. No new dependencies.
- Run tests: `python -m unittest discover -s tests -v`
- A new or changed skill ships only after `code-jig skill-check skills/<name> --review --live` passes on Codex and its `.skill-check` stamp is committed with it; see [AGENTS.md](AGENTS.md).
- Real-tool tests run when `CODE_JIG_REAL_TOOLS=1` is set and lizard, ruff, vulture, knip, gitleaks and osv-scanner are on `PATH`; CI runs them on Linux and Windows. A new parser for an external tool needs a captured-output unit test and, where the tool can run in CI, a real-tool test.
- Read and write files with explicit utf-8; generated files use LF.
- Paths via pathlib; must work with spaces and non-ASCII names on Windows and Linux.
- No code comments.
- Public data rule: no number measured on an employer's machine in any file. Bench or public sources only.
- Clean-room: do not copy content from private overlays or employers into core.
- CI pins @openai/codex@0.162.1, agnix@0.57.0, lizard 1.24.1, ruff 0.17.0, vulture 2.16, knip 6.41.0, gitleaks 8.30.1 and osv-scanner 2.7.0, coverage 7.16.2, zizmor 1.31.1, Node 22 and wrangler 4.151.1 for worker/.
- The core never downloads a tool at run time and runs every tool with its telemetry opt-out.
- `worker/` is infrastructure, not core: it may use Node, but it adds no npm dependencies and has no code comments.
