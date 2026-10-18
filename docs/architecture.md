# Architecture

code-jig is a configuration generator plus a set of small local tools, all in one Python standard-library package (`codejig/`). It never sits between the user and the model: it writes files that Codex and Claude Code read, and it runs as short-lived commands or agent hooks. There is no daemon, no server and no runtime dependency.

## Components

| Component | Modules | What it does |
|---|---|---|
| Entry point | `__main__.py`, `paths.py` | One argparse command line (`code-jig`, alias `cjig`) that dispatches to the subcommands below and finds the core, the overlay and the Codex home. |
| Core and overlay | `overlay.py`, `tiers.py`, `core/`, `skills/`, `overlay-examples/` | The core is shared and versioned (rules, tiers, subagent roles, skills). The overlay is the user's private directory with fixed slots, pinned to a core version. |
| Installer | `install.py`, `atomicwrite.py`, `managed.py` | Renders `AGENTS.md`, the tier profiles, subagent roles, exec-policy rules, skills and hook entries from core plus overlay, and writes them atomically. A file it did not generate is moved aside, never overwritten. |
| Doctor | `doctor.py`, `probe.py` | Checks the Codex binary, the pins, every tier against the account catalog, the generated files, and the installed package against its release digest. |
| Agent hooks | `hooks.py`, `watermark.py`, `humanize.py`, `feedback.py`, `collect.py` | Run after each agent turn or write: strip attribution and invisible characters, report syntax errors and removed tests back to the model, and collect token usage. They fail open so a hook error never breaks the agent. |
| Git gate | `gitgate.py`, `scrub.py` | Opt-in git hooks that strip AI attribution from commit messages, clean staged files, and refuse a push that fails the configured test command. |
| Usage store | `collect.py`, `tokens.py`, `evidence.py` | Reads Codex session files into a local SQLite database and reports tokens, Guardian share, rework and cost. Nothing leaves the machine. |
| Code quality tools | `analyze.py`, `trace.py`, `clike.py`, `review.py` | Run the analyzers already on the machine and group their findings, trace requirement IDs to tests, and send a diff to a model of another family for read-only review. |
| Skills and sources | `skillcheck.py`, `skilllint.py`, `sources.py`, `rewrite.py` | Lint and prove skills on Codex, check that quoted sentences are on the cited pages, and rewrite flagged comment text through an OpenAI-compatible gateway. |

## Data flow

1. The user (or CI) runs `code-jig install`. The installer reads the core and the overlay, renders the files, and writes them into the Codex home, the skills directory and, when asked, the Claude Code settings.
2. Codex or Claude Code starts, reads the generated files, and runs hooks as `code-jig hooks ...` after tool calls. Hook input arrives as JSON on stdin.
3. `collect` appends to the local SQLite store under the user's data directory. `tokens`, `evidence` and `doctor` read it back.
4. `analyze`, `trace`, `check-sources` and `cross-review` are run on demand against a checkout or a list of URLs, and print a report.

## Trust boundaries

- The core, the overlay and the user's own configuration are trusted: the user chose them. An overlay `allow` rule is the user's decision.
- Everything an agent or a repository produces is untrusted input: hook JSON, Codex session files, files under analysis, analyzer output, fetched web pages and model replies. Each is parsed defensively and a malformed record is skipped or quarantined, not executed.
- The network is touched in two places: `check-sources` reads public pages, and `humanize --rewrite` posts comment text to a gateway the user names. Everything else is local.

## Release path

A `vX.Y.Z` tag on `main` runs `.github/workflows/release.yml`: the full CI and the fuzzers, then one wheel built from `git archive` of the tag with hash-locked build tools, an SPDX SBOM, `SHA256SUMS`, a Sigstore signature per file and SLSA provenance, a GitHub release, and, after approval of the `pypi` environment, the same wheel on PyPI. The wheel carries a `VERSION` file with the package digest that `doctor` re-checks after install.

See [security.md](security.md) for what users can expect, [assurance-case.md](assurance-case.md) for why it holds, and the decision records in [adr](adr).
