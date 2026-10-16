# 0026: Every skill passes a Codex review and a live Codex run before it ships

Status: accepted (2026-10-15)

## Decision

A skill in `skills/` ships only with a current `.skill-check` stamp, written by `harness skill-check skills/<name> --review --live` when all of these pass:

- static: the skill lint (0023), no name that exists only in Claude Code (Task or Agent tool, `subagent_type`, `TodoWrite`, `AskUserQuestion`, `WebFetch`, `~/.claude` and others, each reported with the Codex equivalent), every `harness <command>` in a code span is a real command, and an `evals.toml` with at least one case;
- review: a Codex session on the `review` tier, read-only and ephemeral, judges the skill's files against a six-rule rubric about Codex tools, sandbox, triggering, order and Windows, and must end in `VERDICT: ship`;
- live: the installed copy matches the source, and each case runs as `codex exec --json` in a scratch git repository (optionally a fixture folder from `evals/` and declared commits), and the event stream must show the skill's `SKILL.md` being read, the expected commands, at least the expected number of `spawn_agent` calls, and the expected patterns in the final answer. Codex 0.162 leaves `spawn_agent` out of the `--json` stream (only `wait` shows), so live runs are not ephemeral and the spawns are counted from that thread's session log in `CODEX_HOME/sessions`; each live run leaves one there.

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

- A case cannot run a program on the checking machine (security review of the first version): the prompt goes to `codex exec` on stdin, so one starting with `-` is never read as an option such as a sandbox bypass; the shell `setup` list became declarative `commits` made with fixed git commands, hooks off and the message on stdin, because even git-only setup can run programs through aliases or `core.fsmonitor`; a fixture must be a folder directly inside `evals/` and is copied without `.git`.

- Claude stood in for Codex once, at the user's request (2026-10-15). The account's limit ended the third run with 8 skills left. Claude reviewers, one per skill in a fresh context, got the same rubric and material as the Codex review and were rerun until each said `VERDICT: ship`; their stamps say `"reviewer": "claude"` and `"live": "not run"`. `stamp_current` accepts them, so a rerun of `harness skill-check --review --live` with Codex replaces them. Live runs from the third Codex run before that: 5 of the 8 passed; `bug-hunt` failed on a case that expected `average([])` to be reported (an empty-list error is defensible, the case now checks only `last_n`); `skill-validate` and `web-consensus` spawned no subagents, because Codex's `spawn_agent` description forbids spawning unless a skill asks for subagents explicitly and advises doing blocking work locally. Both skills now ask outright.

- Second review (Fable, 2026-10-15, v0.10.1). The review prompt closed the untrusted block with a fixed `MATERIAL>>>`, so a skill could close it itself and dictate the verdict; the markers are now random per run. A live case runs whatever commands Codex chooses from its prompt, under the user's login and with read access to the home directory, so `--live` outside the core `skills/` needs `--trust-evals`. Fixtures may not be or hold symlinks or junctions, `evals/` included (v0.10.2: the first check looked only inside the fixture, so a fixture folder linked to the home directory was copied whole). The stamp gained a digest of `evals.toml` and `evals/`, so emptying the cases makes it stale; existing stamps got it after `git log` showed no eval changed since each stamp. Also fixed: a hung review raised a traceback, Windows paths never counted as reading SKILL.md, wrongly typed case fields crashed after a paid run, nested files named `evals.toml` or `.skill-check` were dropped from install, `check-sources` reported success on a pattern that matched nothing, and non-ANSI Codex output could crash printing on Windows. Not fixed: a catastrophic `output` regex can still hang the checker; it comes from `evals.toml`, which now needs `--trust-evals` outside the core. A stamp is plain JSON, so a hand-written one passes the test; the history of the commit that adds it is the record.

- The Codex rerun of the eight (2026-10-16) replaced every Claude stamp. Codex's review found more in seven of them (PSRule expansion and `-Format File`, `az`/`gh` login checks and exported-ID fallback, pauta approval before a full draft, the published commit and worktree cleanup in `redacao`, Vitest/Jest report paths, the pass 3 skip in `skill-validate`, no single-model fallback in `web-consensus`). The "0 subagents" failures were the checker's: the spawns happened and were not in the JSON stream.

## Cost

About 250 lines, sixteen tests with a fake `codex`, one `evals.toml` and small fixtures per skill. Each live case costs a real Codex turn on the account's quota; the stamp records the Codex version and date.

## Rejected

- Running the live cases in CI: needs a Codex login and quota in CI.
- Trusting the Claude-side `skill-validate` pass alone: it judges the text, not whether Codex can run it.
- A stamp without a digest: it could not tell that a skill changed after its check.
