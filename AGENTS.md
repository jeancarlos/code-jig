# Working on codex-harness

These rules apply to any agent changing this repository, Codex or Claude Code.

## Skills ship only after Codex has run them

The skills here run in Codex, whose tools differ from Claude Code's: commands go through `exec`, edits through `apply_patch`, subagents through `spawn_agent` with an `agent_type` (`explorer`, `reviewer`, `judge`, `default`, `worker`), the plan through `update_plan`. A skill that reads well in Claude can name tools Codex does not have.

Every skill added or changed under `skills/`:

1. Has an `evals.toml` with at least one `[[case]]`: a prompt that should trigger it, and what a working run shows (commands run, subagents spawned, a pattern in the answer). Fixtures go in `evals/<name>/`.
2. Passes `harness skill-check skills/<name>` (lint, names Codex does not have, unknown `harness` commands, evals).
3. Is installed (`harness install`) and passes `harness skill-check skills/<name> --review --live`: a Codex review on the `review` tier that must end in `VERDICT: ship`, then each case run through `codex exec`. Success writes `skills/<name>/.skill-check`.
4. Is committed together with that `.skill-check`. `tests/test_skillcheck.py` fails when a skill's content no longer matches its stamp, so a changed skill cannot pass CI without a new run.

A failing review or case is fixed in the skill, never by loosening the case until it passes. A case that cannot pass in a sandbox (network, escalation) checks that the step was attempted, and says so in its prompt or expectations.

## Other rules

See [CONTRIBUTING.md](CONTRIBUTING.md): stdlib only, no code comments, explicit utf-8, the public data and clean-room rules.
