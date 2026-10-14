# 0007: Tiers are generated Codex profile files

Status: accepted (2026-10-14)

## Decision
`core/tiers.toml` maps each tier (`default`, `deep`, `bulk`, `review`) to a reasoning effort. The overlay's `profiles.toml` maps the same tiers to model IDs. `harness install` writes one `$CODEX_HOME/<tier>.config.toml` per tier with `model`, `model_reasoning_effort` and the Guardian settings from 0008. The tier is chosen when a session starts, with `codex --profile <tier>`. The user's `config.toml` is never edited. A user file that already has a tier's name is moved to a timestamped backup.

## Reason to exist
Effort should match the kind of work, and model IDs differ per account, so the core cannot hard-code them.

## Data
- Since Codex 0.134, a profile is a separate file `$CODEX_HOME/<name>.config.toml`, loaded as a full config layer over `config.toml` (`codex-rs/config/src/loader/mod.rs`, rust-v0.162.1).
- `--profile <name>` is refused when `config.toml` still has `profile = "<name>"` or `[profiles.<name>]` (same file).
- A missing profile file is accepted silently: `codex --profile missing debug prompt-input` exits 0 on the bench.
- Changing reasoning effort, tools or compaction changes the cached prompt prefix (OpenAI prompt-caching guide), so tiers are per session, never switched mid-session.
- Valid efforts come from each model's `supported_reasoning_levels` in `models_cache.json`; they differ per model.

## Cost
About 60 lines of Python and two small TOML files. Doctor checks every tier (0010).

## Kind
Script (generation) and static data.

## Rejected alternatives
- The legacy `[profiles]` table in `config.toml`: rejected at runtime with `--profile`.
- Editing `config.toml`: it belongs to the user, and Codex rewrites parts of it.
