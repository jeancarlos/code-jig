# Contributing

## How to contribute

- Bugs and enhancement requests: open an issue at <https://github.com/jeancarlos/code-jig/issues>. Vulnerabilities go through [SECURITY.md](SECURITY.md), never a public issue.
- Changes: branch `feature/*`, `fix/*` or `chore/*` off `develop`, open a pull request into `develop`. `develop` is merged into `main` and a tag `vX.Y.Z` publishes the release.
- Every code change ships with a test that fails without it. CI runs the unit tests on Linux and Windows, Python 3.11 and 3.13, plus real-tool checks, CodeQL, gitleaks, osv-scanner, zizmor, REUSE and fuzzing.
- Contributions are accepted under the Apache-2.0 license, and every file is covered by `REUSE.toml`.
- Secure design: the core is configuration and stdlib Python, runs no network calls except the documented bootstrap download and source check, refuses non-public addresses, verifies sha256 before unpacking and rejects archive paths outside the target. Common errors to avoid: shell injection (subprocess lists, never user text in a shell), path traversal, unchecked archive members, secrets in files.

## Rules

- Python 3.11+, stdlib only. No new dependencies.
- Run tests: `python -m unittest discover -s tests -v`
- A new or changed skill ships only after `code-jig skill-check skills/<name> --review --live` passes on Codex and its `.skill-check` stamp is committed with it; see [AGENTS.md](AGENTS.md).
- Real-tool tests run when `CODE_JIG_REAL_TOOLS=1` is set and lizard, ruff, vulture, knip, gitleaks and osv-scanner are on `PATH`; CI runs them on Linux and Windows. A new parser for an external tool needs a captured-output unit test and, where the tool can run in CI, a real-tool test.
- Read and write files with explicit utf-8; generated files use LF.
- Paths via pathlib; must work with spaces and non-ASCII names on Windows and Linux.
- No code comments.
- Public data rule: no number measured on an employer's machine in any file. Bench or public sources only.
- Clean-room: do not copy content from private overlays or employers into core.
- CI installs its tools from hash-locked files: `ci/*.txt` (pip, `uv pip compile --universal --generate-hashes ci/<name>.in -o ci/<name>.txt`) and `ci/npm/package-lock.json` (`npm install --package-lock-only --ignore-scripts` in `ci/npm`). Bump a version in the `.in` file or `package.json`, regenerate, commit both. gitleaks 8.30.1 and osv-scanner 2.7.0 are downloaded with a sha256 check, Node is 22 and wrangler is 4.151.1 for worker/.
- The core never downloads a tool at run time and runs every tool with its telemetry opt-out.
- `worker/` is infrastructure, not core: it may use Node, but it adds no npm dependencies and has no code comments.
- Lint exceptions in `ruff.toml`: `tests/fixtures` is captured install output, so it is data and not linted. UP036 is ignored in `bootstrap.py`, `codejig/__main__.py` and `codejig/install.py` because their version guards must run on older Pythons to print the "Python 3.11 or newer" message. BLE001 is ignored in `codejig/collect.py`, `codejig/hooks.py`, `codejig/humanize.py` and `codejig/watermark.py` because agent hooks fail open by design, so a hook error never breaks the agent turn. TRY004 is ignored in `codejig/analyze.py` and `codejig/overlay.py` because `ValueError` is the documented config-error contract that callers catch.
