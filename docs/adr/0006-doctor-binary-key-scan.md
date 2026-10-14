# 0006: Doctor scans the native binary for config keys

Status: accepted (2026-10-14)

## Decision
`doctor --check-binary` scans the native Codex binary for every key the pack uses or will write. It rejects launchers smaller than 1,000,000 bytes. Without that flag, `doctor` also checks the core pin and that the core is clean, and audits the `AGENTS.md` chain against `project_doc_max_bytes`.

## Reason to exist
Codex is alpha and config keys change. A renamed key is ignored silently, so the pack would keep working on paper and do nothing.

## Data
- Legacy profile fields are still in the schema but rejected at runtime. A schema check is not enough, so step 2 adds behaviour probes.
- npm installs a small launcher in front of the native binary. Scanning the launcher finds no keys, hence the size floor.
- The `AGENTS.md` chain stops growing once `project_doc_max_bytes` (32 KiB default) is reached, with no warning.

## Cost
A string scan of a large binary. It can miss a key that is built at runtime, which behaviour probes will cover. CI runs it against the pinned `@openai/codex@0.162.1`.

## Kind
Script.

## Rejected alternatives
- Trust the published JSON schema. It lists fields the runtime rejects.
- Run Codex and inspect behaviour only. Slower and needs quota. Kept as a step-2 addition, not a replacement.
