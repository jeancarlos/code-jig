---
name: skill-validate
description: Use when a SKILL.md is about to ship or was just edited, when a skill is reviewed or audited, when a skill seems ignored, skipped or misread by agents, or when the user says "validate this skill", "lint the skill", "check my skill", "is this skill any good".
---

# Validate a skill

Three passes. A script decides everything a pattern can decide; a reviewer from another model family decides the rest, in a fresh context, because the author of a skill already knows what it meant to say.

## Pass 1: mechanical

```sh
harness lint-skill path/to/skill-dir
```

`FAIL` breaks loading or a hard rule and exits 1. `WARN` is a judgement call. Run pass 2 whatever pass 1 says: its FAILs go in the report with everything else.

## Pass 2: judgement

This skill asks for a subagent: call `spawn_agent` with `agent_type` `reviewer` and a message holding the full SKILL.md text and this rubric, then wait for it. Do not fork this conversation into it, and do not judge the rubric yourself instead.

| # | Rule |
|---|---|
| 1 | The description states triggering conditions only. A description that summarises the workflow becomes a shortcut agents take instead of reading the body. |
| 2 | Every rule the skill enforces is reachable from the body, not only from the description. |
| 3 | Guidance matches the failure: a rule broken under pressure needs a prohibition and the excuses it answers; wrong-shaped output needs a recipe naming the parts in order; an omitted element needs a slot in a template. |
| 4 | No clause that reopens a rule ("unless it matters", "where appropriate"). |
| 5 | No narrative: no session logs, dated stories, "we found this once". |
| 6 | Reference an agent can act on, not the author's reasoning. |
| 7 | One worked example, not the same pattern repeated per language. |
| 8 | Flowcharts only for non-obvious decisions; tables and lists carry reference. |
| 9 | Words a searching agent would type appear early: error strings, symptoms, tool and command names. |
| 10 | Heavy reference and scripts sit in their own files, named from SKILL.md. |

Require one line per rule, `N | PASS or FAIL | shortest quote that decides it | one-line fix`, then `VERDICT: ship` or `VERDICT: fix N, N`. Prose instead of rows means the contract was not stated firmly enough: restate it and spawn again.

## Pass 3: Codex runs it

A skill that reads well can still name tools Codex does not have, or never trigger. After pass 2 passes and the skill is installed (`harness install`):

```sh
harness skill-check path/to/skill-dir --review --live
```

It needs an `evals.toml` next to SKILL.md with at least one `[[case]]` (`prompt`, and any of `commands`, `output`, `spawns`, `fixture`, `commits`, `sandbox`). It runs a Codex review on the `review` tier, then each case through `codex exec`, and writes `.skill-check` when everything passes. In the codex-harness repository that stamp is required in the same commit as the skill.

## Report

Merge all three passes into one table: every FAIL and WARN, every rubric row, the Codex review verdict and each live case. Validation edits nothing. When the user asks for the fixes, apply them and run all three passes again.

## Common mistakes

| Mistake | Instead |
|---|---|
| Judging in the context that wrote the skill | Pass 2 runs in a fresh `reviewer`. |
| Treating every WARN as a defect | A reference skill may be long; the word count prompts a split, it does not demand one. |
| Accepting "looks good" | The contract is rows with quotes. No quote means it was not read. |
| Skipping pass 2 | No pattern can see a description that summarises the workflow, the defect that costs the most. |
