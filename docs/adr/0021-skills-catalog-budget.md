# 0021: Doctor measures the skills catalog

Status: accepted (2026-10-15)

## Decision

The zero-token prompt probe (`codex --profile <tier> debug prompt-input`) also measures the `<skills_instructions>` block of the first tier that loads. Doctor reports its size and skill count, and warns above 8,000 bytes with the five largest entries and the fix: `[[skills.config]] name = "<skill>" enabled = false` in `config.toml`. The harness does not disable skills itself.

## Context

On the bench, every request carried 13,137 bytes of skills catalog for 41 skills, many of them unrelated to coding. Most of it is served from the prompt cache, but it is still processed on every request and competes for the model's attention with the task.

## Data

- `[[skills.config]]` takes a `name` or `path` and `enabled`; `[skills] max_context_tokens` caps the catalog, by default at 2% of the context window and at most 10,000 tokens (`config/src/skills_config.rs`, rust-v0.162.1).
- The catalog lists each skill as `- <name>: <description> (file: ...)`; plugin skills carry a `plugin:skill` name (bench, `debug prompt-input`).
- `include_apps_instructions` and `include_collaboration_mode_instructions` would save about 1.2 KB more, but they turn off features, so they are left alone.

## Cost

About 25 lines in `probe.py`; no extra Codex call.

## Rejected

- An overlay list of skills to disable: `config.toml` already has the setting, and which skills a machine needs is the user's call.
- Setting `max_context_tokens`: Codex then drops skills by its own order, not by what the user uses.
