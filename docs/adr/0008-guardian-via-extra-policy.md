# 0008: Guardian on every tier, overlay policy as additions

Status: accepted (2026-10-14)

## Decision
Every tier profile sets `approvals_reviewer = "auto_review"`. The reviewer model stays `codex-auto-review`. The overlay's `guardian-policy.md`, when present, becomes `[auto_review].extra_policy`. `[features.guardianv2]` stays off until a bench A/B (step 3) shows fewer tokens per review with no rise in wrong allows or denials.

## Reason to exist
Guardian reviews sandbox escalations automatically instead of asking the user. Each machine needs its own additions (company hosts, release rules) without losing the upstream rules.

## Data
- `extra_policy` is rendered into the `{{ extra_policy }}` slot of the Guardian template next to the resolved upstream policy (`codex-rs/core/src/config/mod.rs`, `codex-rs/prompts/src/guardian_instructions.rs`, rust-v0.162.1). `[auto_review].policy` replaces the upstream policy instead.
- A managed `guardian_extra_policy` in `requirements.toml` takes precedence over the user's `extra_policy` (same config file). Doctor warns when one is present.
- The reviewer model comes from the parent model's catalog field `auto_review_model_override` and falls back to `codex-auto-review`; the only override is replacing the model catalog.

## Cost
Config only. The generated profile carries the policy text as one TOML string.

## Kind
Static (generated).

## Rejected alternatives
- Vendoring the upstream policy into `[auto_review].policy` plus a `policy-diff` command: it replaces upstream, goes stale with each Codex release, and needs a command to notice. `extra_policy` keeps upstream by construction.
- Overriding the Guardian model with `model_catalog_json`: undocumented, and changing who reviews security on a managed laptop is tampering with a security control.
