# 0017: Evidence that the harness pays off

Status: accepted (2026-10-15)

## Decision

`harness evidence` compares, per repo, commits made inside a Codex session's time window (start to last activity, plus two hours) with the same repo's other commits. For each group it reports rework (a revert, a `fixup!` or `squash!`, or the same lines changed again within 14 days) over commits at least 14 days old, and, with `--analyze N`, `analyze` findings per 100 changed lines on N sampled commits. It also reports test runs and their pass rate, skill reads, Guardian outcomes, escalations, and tokens per session and per harness commit. A group with fewer than 20 mature commits gets no rate.

The tracker records the extra facts it needs: each command's exit code and the skill it read go to a new `call_results` table (read through `call_view`), and Guardian outcomes to a new `guardian` table. The `calls` table is unchanged, so an older collector (a `Stop` hook not yet reinstalled, or a rolled-back core) keeps writing to the same database. `evidence` runs `collect` first. No hook was added.

## Context

The harness is meant for daily work on a managed laptop, and the question was whether it is worth its tokens there. The tracker already held tokens, commands, escalations and Guardian threads; what was missing was the outcome. The repos' own git history is the cheapest baseline that needs nothing from the user: the same people, the same code, before and outside the sessions.

A dogfood run on 2026-10-15 shaped two details. Codex hit its usage limit mid-turn, and a turn that ends in an error does not fire the `Stop` hook, so `evidence` collects before it reports. Running the new collector against the live database first added columns to `calls`, and the installed hook then failed on every command, which is why the new facts live in their own table.

## Rejected

- Snapshots in the `Stop` hook (tests and `analyze` at the end of every turn): slow, flaky, and it would block Codex.
- An A/B bench of the harness against stock Codex on fixed tasks: stronger evidence, but not chosen now. It can grow out of `bench/smoke.py`.
- A trend-only report with no baseline: cheapest, but it cannot tell the harness from the weather.
- Adding columns to `calls`: breaks older collectors writing to the same database.
