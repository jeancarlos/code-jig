# 0025: web-consensus routes each job to a role, and a script checks every quote

Status: accepted (2026-10-15)

## Decision

The `web-consensus` skill assigns each job to the role whose tier fits it: researchers and cold verification to `explorer` (bulk tier), the challenger to `reviewer` (review tier), and the verdict to a new `judge` role on the deep tier. `install` writes `judge.toml` like the other roles (0018), with the skills catalog, apps, plugins and memories turned off. Evidence is written as JSON lines (`claim`, `url`, `quote`), and `harness check-sources FILE...` fetches each URL once and reports per claim: `ok` when the normalised page text contains the normalised quote, `quote-missing`, `dead`, `blocked` (401, 403, 429, 451), `unreadable` (non-text content), `bad-url` (anything but http and https), `no-quote` or `malformed`. It exits 1 when any claim is dead, mismatched or malformed.

## Context

The user asked that web-consensus use subagents, each on the best model for its job, on both the public and the work catalog. In dev-harness the same skill ran three models through a gateway that does not exist on a managed machine. The tiers already map to each catalog (0018), so roles carry the routing to either one. The step that compared quotes with pages was a model reading `curl` output; a script does it exactly.

## Data

- Page text comes from `html.parser` with `script`, `style`, `noscript` and `template` skipped and entities decoded; normalisation folds curly quotes, dashes and no-break spaces and collapses whitespace, so a quote copied from the rendered page matches.
- A live run against docs.python.org confirmed a real quote and rejected a fabricated one (2026-10-15).
- Codex sets `CODEX_SANDBOX_NETWORK_DISABLED=1` in a sandbox without network; the command stops at once and asks for an escalated run, so one Guardian review covers every URL instead of each fetch timing out.
- `urllib` honours the proxy variables and, on Windows, the system certificate store, which a TLS-inspecting corporate network needs.

## Cost

About 130 lines, seven tests against a local HTTP server, one role file, a rewritten skill.

## Rejected

- Judging in the main session: its tier is whatever the user started, often not the strongest.
- A JSON report option: the text table is what the model reads; add it when a script needs it.
- Parsing PDFs: no standard-library parser; `unreadable` asks for a second source instead.
