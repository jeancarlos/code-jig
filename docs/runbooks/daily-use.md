# Runbook: daily use

## Shell setup

Add to your shell profile, with your own paths:

```sh
export CODEX_HARNESS_OVERLAY=~/codex-overlay
alias harness='PYTHONPATH=~/codex-harness python3 -m harness'
alias cx='codex --profile default'
```

## Start every session with a tier

Plain `codex` uses only `config.toml`: no tier model, no Guardian. Start with a profile instead:

| Command | Use it for |
|---|---|
| `codex --profile default` | Everyday work. |
| `codex --profile deep` | Hard bugs, design, unfamiliar code. |
| `codex --profile bulk` | Mechanical work you hand off explicitly: renames, boilerplate, bulk edits. |
| `codex --profile review` | Reviewing, with a model from another family where the account has one. |

Keep one tier and one task per thread. Switching model or reasoning effort mid-thread throws away the prompt cache, and a long thread re-sends its whole history on every request. When the topic changes, start a new thread.

## Skills

Installed into `~/.agents/skills`, picked up by every session. Ask for them by name or with the phrases in their descriptions:

| Skill | When |
|---|---|
| `cross-review` | Before you commit a plan, design or diff, get a review from a model of another family. |
| `grilling` | Stress-test a plan or decision; it asks at most three questions per round and keeps the settled answers. |
| `web-consensus` | Settle a factual question against live sources instead of memory. |
| `improve` | "Remember this", "make this a rule": turns a lesson into an overlay change, then reinstalls. |

superpowers (`codex plugin add superpowers@openai-curated-remote`) adds brainstorming, planning, TDD and debugging workflows.

## Review your own change before pushing

```sh
harness cross-review                 # uncommitted changes against HEAD
harness cross-review --base main     # the whole branch
harness cross-review src/a.py docs/b.md
```

It runs the `review` tier read-only and prints findings. Verify each one before acting. New files that were never added are not in `git diff`; run `git add -N <file>` first so they show up.

## The repo's own AGENTS.md

Codex reads `AGENTS.md` from the repo root down to the current directory, after the global one. Keep the repo's file short and concrete: how to build, test and lint, where things live, what not to touch. `harness doctor`, run inside the repo, shows how much of the 32 KiB budget the chain uses.

## When something looks wrong

| Symptom | Go to |
|---|---|
| Codex stops a turn after denials | [circuit-breaker](circuit-breaker.md) |
| Wrong model, missing skills, stale files | [doctor](doctor.md) |
| Usage higher than expected | [tokens](tokens.md) |
| Cannot reach the network, certificate errors | [network-and-certificates](network-and-certificates.md) |
| After a Codex or core update | [upgrade-and-rollback](upgrade-and-rollback.md) |
| Commits or PRs carry Codex attribution | [commit-attribution](commit-attribution.md) |
