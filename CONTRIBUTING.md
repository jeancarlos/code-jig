# Contributing

- Python 3.11+, stdlib only. No new dependencies.
- Run tests: `python -m unittest discover -s tests -v`
- Read and write files with explicit utf-8; generated files use LF.
- Paths via pathlib; must work with spaces and non-ASCII names on Windows and Linux.
- No code comments.
- Public data rule: no number measured on an employer's machine in any file. Bench or public sources only.
- Clean-room: do not copy content from private overlays or employers into core.
- CI pins @openai/codex@0.162.1 and agnix@0.57.0.
