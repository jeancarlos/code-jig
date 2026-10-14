# 0010: Doctor checks tiers, managed requirements and Codex itself

Status: accepted (2026-10-14)

## Decision
`harness doctor` adds:
- per tier: the profile file exists and is current; the model is in this account's `models_cache.json` and supports the tier's effort (candidates are listed, never picked); `config.toml` has no legacy profile with a tier's name; `review` and `default` use different model families;
- the local managed `requirements.toml` (`/etc/codex/` on Linux and macOS, `%ProgramData%\OpenAI\Codex\` on Windows): FAIL when `auto_review` is not an allowed reviewer; warn when `auto_review.ignore_rules` names a tier model, when `allow_managed_hooks_only` is set, or when a managed `guardian_extra_policy` overrides the overlay; and a key-level diff against `bench/requirements.toml`;
- a zero-token probe per tier, `codex --profile <tier> debug prompt-input ping`: the profile parses and the generated `AGENTS.md` reaches the prompt;
- `--live`, opt-in: one short `codex exec --profile <tier> --ephemeral --sandbox read-only` per tier, checking the `model:` and `reasoning effort:` lines Codex prints before the turn.

## Reason to exist
Each of these fails silently in Codex: a missing profile, a model the account does not have, an `AGENTS.override.md` or size cap that hides the generated file, a managed lock that disables Guardian, rules or hooks.

## Data
- `debug prompt-input` accepts `--profile`, exits 1 on a malformed profile, and its output contains the global `AGENTS.md` text including the marker line (bench, 0.162.0-alpha.17.2).
- `codex exec` prints the effective model and reasoning effort before submitting the turn (`codex-rs/exec/src/event_processor_with_human_output.rs`, rust-v0.162.1).
- Requirements keys and paths: `codex-rs/config/src/config_requirements.rs` and `loader/mod.rs`. `ignore_rules` lists model slugs for which allow rules are ignored (`core/src/session/turn_context.rs`).
- Cloud-delivered requirements exist and are not visible in any file; doctor says so.

## Cost
About 200 lines across `doctor.py`, `managed.py` and `probe.py`. The prompt probe takes about a second per tier. `--live` spends a short turn per tier on the account's quota.

## Kind
Script.

## Rejected alternatives
- Checking the published schema only: it accepts fields the runtime rejects.
- Running the live probe by default: it spends quota on every doctor run.
