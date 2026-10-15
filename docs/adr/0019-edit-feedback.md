# 0019: Edit feedback from the write hook

Status: accepted (2026-10-15)

## Decision

The `PostToolUse` write hook (watermark and humanize) also reports, through `additionalContext`:

- errors in each file the tool wrote: `.py` with `ruff check --isolated --no-cache --select E9,F63,F7,F82` when ruff is on `PATH` and resolves outside the workspace, otherwise an `ast` parse; `.json` and `.toml` with the standard library. At most 10 lines per file, files over 1 MB skipped;
- test tampering: a Codex patch that deletes a test file or adds a skip marker, or a Claude Code `Edit`/`MultiEdit` whose new text adds a skip marker the old text did not have.

Nothing blocks, reverts or retries. The code lives in `harness/feedback.py`.

## Context

A linter guard on edits raised SWE-agent's resolve rate by about 3 points (arXiv 2405.15793). Failed runs cost 1.3 to 5.4 times the tokens of successful ones (arXiv 2511.11012), so catching a broken edit at the write is cheaper than finding it several turns later. Agents that can edit tests tamper with them (arXiv 2605.21384); read-only tests stopped it (arXiv 2606.07379). The user rejected blocking gates (ADR 0016), so the hook informs and the agent decides.

## Data

- `PostToolUse` output can block and add context, but cannot replace the tool's output (`hooks/src/events/post_tool_use.rs`, rust-v0.162.1).
- Hooks run outside the sandbox (ADR 0012). eslint configs and plugins, tsc plugins, `dotnet build` and anything in `node_modules/.bin` execute code the agent can write, so the hook runs none of them. Ruff reads configuration but executes none, and `--isolated` stops it reading even that; the select list is flake8's fatal set (syntax errors, undefined names, invalid comparisons).
- A `ruff` that resolves inside the workspace is skipped, because the agent could have written it. A `ruff` elsewhere on `PATH` that the sandbox lets the agent write (for example when the workspace root is the home directory) is the remaining ceiling.
- Guardian sees only commands that escalate (ADR 0009), not file edits, so a Guardian policy line could not catch test edits.

## Cost

About 150 lines and one test file. Ruff on one file takes milliseconds; the hook's timeout stays at 10 seconds.

## Rejected

- Blocking the write (`decision: block`) or a `Stop` gate: the user wants feedback, not gates.
- TypeScript and C# checks in the hook: every option runs repository code or is too slow; `harness analyze` covers them on request.
- Comparing a full-file `Write` against the previous content: the hook only sees the result.
