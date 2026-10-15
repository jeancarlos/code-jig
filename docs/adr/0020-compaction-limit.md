# 0020: An optional compaction point, and no custom compaction prompt

Status: accepted (2026-10-15)

## Decision

`overlay.toml` may set `auto_compact_token_limit`, a positive integer. `install` writes it into every tier profile as `model_auto_compact_token_limit`; doctor compares the profiles with it. The core sets no value, and neither example overlay does. `compact_prompt` is not used.

## Context

Codex compacts at 90% of the model's context window by default: about 245K tokens for the 272K models in the bench catalog (`auto_compact_token_limit` in `protocol/src/openai_models.rs`, rust-v0.162.1). Sessions that sit around 110K tokens therefore never compact and re-send their whole history on every request. Observation masking matched LLM summarisation at about half the cost in one study (arXiv 2508.21433), but Codex has no masking and a hook cannot rewrite tool output (ADR 0019). An earlier compaction point is the one lever left, and no measurement yet says which value helps without losing detail, so it is opt-in.

## Data

- `model_auto_compact_token_limit` is read per layer, so a profile can set it (`config/src/config_toml.rs`), and the limit applies to both local and remote compaction (`core/src/session/context_window.rs`).
- `compact_prompt` replaces the summarisation prompt only for local compaction (`core/src/compact.rs`, `core/src/tasks/compact.rs`). OpenAI providers use remote compaction v2 (`model-provider/src/capabilities.rs`, `core/src/session/turn.rs`), so on both target machines it would be silently ignored.
- `harness tokens` already counts compactions per session, and `harness evidence` reports rework, so a value can be judged before and after.

## Cost

Ten lines in `overlay.py`, `tiers.py`, `install.py` and `doctor.py`.

## Rejected

- A core default: no bench number supports one.
- `compact_prompt`: ignored on OpenAI providers.
- `PreCompact`/`PostCompact` hooks that write a handoff file: no measured need yet.
