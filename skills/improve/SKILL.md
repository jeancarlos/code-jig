---
name: improve
description: Use when the user asks to improve the harness, its rules, Guardian policy, skills or knowledge from experience on this machine, or says "remember this for next time", "make this a rule", "teach the harness".
---

# Improve

Turn something learned into a durable change, in the right place, without leaking what must stay local.

## Start

1. Run `python -m harness doctor` and fix any FAIL first.
2. Read `overlay.toml` in the overlay (`$CODEX_HARNESS_OVERLAY`, in PowerShell `$env:CODEX_HARNESS_OVERLAY`, or the path the user gives). `core_writable` decides where you may write.

## Where changes go

| Change | Slot |
|---|---|
| A rule every session should follow | `AGENTS.overlay.md` |
| Something Guardian should treat as riskier or safer | `guardian-policy.md` (additions to the upstream policy, never a replacement) |
| A model for a tier | `profiles.toml` |
| A command rule | `rules/<name>.rules`. Prefer `forbidden` rules. An `allow` rule runs the command outside the sandbox with no review, and the agent can change what a test or build command runs, so allow only what you would run unsupervised in that repo. |
| A repeatable workflow | `skills/<name>/SKILL.md`, then run the `skill-validate` skill on it |
| A fact about tools, services or conventions here | `knowledge/<slug>.md`, one fact per file, plus one line in `knowledge/INDEX.md` |

With `core_writable = false`, write only to these overlay slots. Never edit the core checkout. With `core_writable = true` (a bench machine), core edits are allowed, with tests, and are committed in the core repo.

## Knowledge

- One fact per file: what is true, why it matters, how to apply it.
- Before adding, search the index for a file that already covers it, and update that file instead.
- Keep `INDEX.md` at 150 lines or fewer, one line each. Merge related facts and delete ones that are no longer true.

## Finish

1. Run `python -m harness install`, then `python -m harness doctor`.
2. Summarise what changed and where.
3. End with **Upstream candidates**: improvements that would help anyone, written in generic language. Leave out company and product names, hosts, people, numbers measured at work, and code copied from work. The user decides whether to restate them on another machine. Nothing is copied across.
