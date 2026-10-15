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

## Which model for which job

A skill cannot pick its own model: Codex runs it on the session's model. Two things decide the model. The first is the tier you start the session with. The second is the subagent role the session hands work to: `explorer` runs on the `bulk` tier's model and `reviewer` on the `review` tier's (see Subagent roles below).

The picks below follow each model's own description in the account catalog (`models_cache.json`), not a benchmark. "Public" is the catalog of a personal ChatGPT plan; "work" is a narrower enterprise catalog without the frontier model and without the newest workhorse.

| Tier or role | Jobs and skills | Public catalog | Work catalog |
|---|---|---|---|
| `default` | Everyday coding, `regression-tests`, `code-analysis`, `hld-trace`, `codegen`, `improve`, `redacao` | `gpt-6.1-sol` ("latest workhorse for coding and everyday work") | `gpt-6-sol` (the newest workhorse there) |
| `deep` | Root-cause debugging, design, unfamiliar code, `bug-hunt`, `grilling` | `gpt-6-astra` ("frontier intelligence for the most demanding work") | `gpt-6-sol` at `high`: no frontier model, so the effort carries it |
| `bulk`, and every `explorer` | Lookups, searches, web research for `web-consensus`, mechanical edits | `gpt-6-luna` ("fast and affordable for easier tasks") | `gpt-6-luna` |
| `review`, and every `reviewer` | `cross-review`, the `web-consensus` challenger, checking a finding before acting on it | `gpt-6-astra`: the strongest model checks the workhorse's work | `gpt-5.6-sol`: another generation, so different blind spots |

The two example overlays carry these picks: `overlay-examples/personal` for the public catalog, `overlay-examples/enterprise` for the work one. `harness doctor` checks every pick against the account it runs on, and lists the models available when one is missing.

## Subagent roles

`install` writes two roles to `$CODEX_HOME/agents/`. Codex lists them in the spawn tool, with a note that each role's model cannot be changed:

- `explorer` replaces Codex's built-in role of the same name, which runs on the parent's model. Ours runs on the `bulk` tier and answers with `path:start-end` line ranges and short quotes, never whole files. `grilling`, `redacao` and the `web-consensus` researchers use it.
- `reviewer` runs on the `review` tier and only looks for what is wrong. The `web-consensus` challenger uses it.

Code-writing subagents keep the default role, which inherits the session's model. Ask for an explorer when you want one: "use explorers to find every caller of X".

## Skills

Installed into `~/.agents/skills`, picked up by every session. Ask for them by name or with the phrases in their descriptions:

| Skill | When |
|---|---|
| `cross-review` | Before you commit a plan, design or diff, get a review from a model of another family. |
| `grilling` | Stress-test a plan or decision; it asks at most three questions per round and keeps the settled answers. |
| `web-consensus` | Settle a factual question against live sources instead of memory. |
| `improve` | "Remember this", "make this a rule": turns a lesson into an overlay change, then reinstalls. |
| `code-analysis` | "What would Sonar say": runs `harness analyze` and fixes by category. |
| `regression-tests` | Bug fixes and behaviour changes: failing test first, then coverage of the changed lines. |
| `hld-trace` | "Does this follow the design": requirement IDs to tests with `harness trace`. |
| `bug-hunt` | Property tests, fuzzing, mutation testing on the changed files. |
| `codegen` | OpenAPI clients, codemods, scaffolding from a script kept in the repo. |

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
| Analysis tools skipped or erroring | [code-quality](code-quality.md) |
| Cannot reach the network, certificate errors | [network-and-certificates](network-and-certificates.md) |
| After a Codex or core update | [upgrade-and-rollback](upgrade-and-rollback.md) |
| Commits or PRs carry Codex attribution | [commit-attribution](commit-attribution.md) |
