# 0011: The tracker reads Codex rollouts into SQLite

Status: accepted (2026-10-14)

## Decision
`harness collect` reads `$CODEX_HOME/sessions/**/rollout-*.jsonl` and `archived_sessions/` into `$CODEX_HOME/codex-harness/usage.sqlite3`. It keeps a byte offset per file and reads complete lines only. `harness tokens` prints the report: Guardian share of input, reviews and input per review, escalations by command, top sessions with cache hit, model requests, compactions and polling calls, sessions over 300 model requests, and input by model. `dashboard.json` is an optional Grafana board over the same database.

## Reason to exist
Every lever in this pack is judged by these numbers, before and after install. Without a local tracker they come from whatever board a user happens to have.

## Data
- Each model response writes a `token_usage_record` with its own `usage`: input (cached included), cached, output, reasoning (`codex-rs/protocol/src/protocol.rs`, rust-v0.162.1). No cumulative delta math is needed. Older rollouts only have cumulative `token_count` events. For those the collector uses `last_token_usage` and skips a line whose total did not change, because duplicates exist.
- A Guardian review is a persisted child thread: `source = {"subagent": {"other": "guardian"}}`, `thread_source = "guardian_review"`, `parent_thread_id` = the reviewed thread, model `codex-auto-review`. One trunk thread per parent gets one turn per review (bench run, 2026-10-14).
- An escalation is a tool call with `sandbox_permissions: "require_escalated"`. In code mode it sits in the `exec_command({cmd: ...})` text of a `custom_tool_call`, otherwise in `function_call` arguments.
- Bench check: for all five bench threads, the collector's input plus output equals Codex's own `threads.tokens_used` in `state_5.sqlite`, including the old `token_count`-only rollout and the Guardian thread (7,231 input + 112 output = 7,343).

## Cost
About 250 lines (`collect.py`, `tokens.py`), hand-written fixtures, one JSON board.

## Kind
Script.

## Known limits
- When reviews run in parallel, Guardian uses ephemeral forks (`core/src/guardian/review.rs`), which may not be persisted, so the Guardian share is a floor.
- Unknown line types are ignored; malformed known lines are quarantined with path and line, and `tokens` reports the count.

## Rejected alternatives
- ccusage as the collector: it has no Guardian or subagent split and no polling count, and it fetches prices remotely by default. It stays a manual cross-check on the bench.
- Reading `state_5.sqlite`: it holds a per-thread total only, with no per-request rows, models over time or escalations, and its schema is internal.
- Grafana as a requirement: it is a server; the CLI is enough.
