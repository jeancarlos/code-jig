# Contributing

- Python 3.11+, stdlib only. No new dependencies.
- Run tests: `python -m unittest discover -s tests -v`
- Real-tool tests run when `HARNESS_REAL_TOOLS=1` is set and lizard, ruff, gitleaks and osv-scanner are on `PATH`; CI runs them on Linux and Windows. A new parser for an external tool needs a captured-output unit test and, where the tool can run in CI, a real-tool test.
- Read and write files with explicit utf-8; generated files use LF.
- Paths via pathlib; must work with spaces and non-ASCII names on Windows and Linux.
- No code comments.
- Public data rule: no number measured on an employer's machine in any file. Bench or public sources only.
- Clean-room: do not copy content from private overlays or employers into core.
- CI pins @openai/codex@0.162.1, agnix@0.57.0, lizard 1.24.1, ruff 0.17.0, gitleaks 8.30.1 and osv-scanner 2.7.0.
- The core never downloads a tool at run time and runs every tool with its telemetry opt-out.
