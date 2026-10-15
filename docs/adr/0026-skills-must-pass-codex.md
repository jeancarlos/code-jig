# 0026: Every skill passes a Codex review and a live Codex run before it ships

Status: accepted (2026-10-15)

## Decision

A skill in `skills/` ships only with a current `.skill-check` stamp, written by `harness skill-check skills/<name> --review --live` when all of these pass:

- static: the skill lint (0023), no name that exists only in Claude Code (Task or Agent tool, `subagent_type`, `TodoWrite`, `AskUserQuestion`, `WebFetch`, `~/.claude` and others, each reported with the Codex equivalent), every `harness <command>` in a code span is a real command, and an `evals.toml` with at least one case;
- review: a Codex session on the `review` tier, read-only and ephemeral, judges the skill's files against a six-rule rubric about Codex tools, sandbox, triggering, order and Windows, and must end in `VERDICT: ship`;
- live: the installed copy matches the source, and each case runs as `codex exec --json` in a scratch git repository (optionally a fixture from `evals/` and `setup` commands), and the event stream must show the skill's `SKILL.md` being read, the expected commands, at least the expected number of `spawn_agent` calls, and the expected patterns in the final answer.

The stamp holds the skill's tree digest (the same digest `install` uses, so `evals.toml`, `evals/` and the stamp are excluded and never installed). `tests/test_skillcheck.py` fails when any core skill lacks a stamp matching its current content. The rule is written for agents in the repository's own `AGENTS.md`, which `CLAUDE.md` imports.

## Context

The user writes and uses these skills in Claude Code as well as Codex, and asked that every new or improved skill pass a Codex review and a test that shows it works, because Codex exposes different tools. On the bench, Codex 0.162 runs in code mode: commands and patches go through one `exec` tool and subagents through the `collaboration` tools (`spawn_agent`, `send_message`, `wait_agent`, `followup_task`), counted from the bench's own rollouts. A skill naming Claude's tools reads fine to a reviewer who knows Claude and fails in Codex.

## Data

- `codex exec --json` emits `item.completed` events with `command_execution` (`command`, `exit_code`), `collab_tool_call` (`tool`), `agent_message` (`text`) and `turn.completed` with `usage` (`exec/src/exec_events.rs`, rust-v0.162.1).
- Codex has no skill-loading tool; the model reads `SKILL.md` with a shell command, so a read shows up as a command containing `<name>/SKILL.md`.
- The live run sets `approvals_reviewer="user"`, so `codex exec` never escalates; a case whose skill needs the network or an escalation checks that the step was attempted, not that it succeeded.
- CI has no Codex login, so it cannot run the review or the cases; the stamp carries the evidence and CI checks it is current.

- First full run (2026-10-15, Codex 0.162, `gpt-6.1-sol` for the cases, `gpt-6-astra` for the review): the review failed all 12 skills and 8 of 12 live cases passed, at 39K to 172K input tokens per case. Two rubric premises were wrong and were corrected, not relaxed: the reviewer treated `harness` as an outside dependency (the rubric now lists its commands, which the static check verifies), and rule 2 asked every skill to announce escalations, which Codex requests by itself; rule 2 now requires the user's explicit approval only for pushing, publishing, deleting data or rewriting shared history. The review also stopped seeing `evals.toml`, which is not part of the skill. The real findings were fixed in the skills: `NAME=value command` lines with no PowerShell form, `&&` that Windows PowerShell 5.1 lacks, a glob PowerShell does not expand (`check-sources` now expands patterns itself), contradictions between a rule and an exception (`bug-hunt`, `redacao`, `skill-validate`, `web-consensus`), a hard dependency on a personal skill and vault path (`redacao`), a missing branch switch before `git reset --keep`, and a secret rotation done without the user.
- The account's usage limit ended the second run. A Codex `error` or `turn.failed` event is now reported as "the skill was not tested", never as a skill failure.

## Cost

About 250 lines, sixteen tests with a fake `codex`, one `evals.toml` and small fixtures per skill. Each live case costs a real Codex turn on the account's quota; the stamp records the Codex version and date.

## Rejected

- Running the live cases in CI: needs a Codex login and quota in CI.
- Trusting the Claude-side `skill-validate` pass alone: it judges the text, not whether Codex can run it.
- A stamp without a digest: it could not tell that a skill changed after its check.
