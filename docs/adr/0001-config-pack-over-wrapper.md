# 0001: Config pack and installer, not a wrapper

Status: accepted (2026-10-14)

## Decision
Ship codex-harness as a config pack plus a small installer. `harness install` writes files into `CODEX_HOME`. Codex itself runs unmodified.

## Reason to exist
Codex reads files in `CODEX_HOME`. It cannot read an overlay or a pack on its own. Something has to generate and place them, and `doctor` has to check them.

## Data
- Profiles are separate files since Codex 0.134 (`<name>.config.toml`). The legacy `[profiles]` table is rejected at runtime.
- Plugins carry only skills, apps, mcpServers and hooks. This was read from 17 installed plugin manifests. They cannot carry rules, config or `AGENTS.md`.
- `install` backs up a non-generated `AGENTS.md` as `AGENTS.md.bak-<timestamp>[-N]` before writing.

## Cost
A few hundred lines of stdlib Python. The pack must track Codex config changes, which `doctor` checks.

## Kind
Script.

## Rejected alternatives
- Wrapper CLI over `codex exec` or app-server. Much more code against an alpha protocol.
- Fork of dev-harness. Its opencode plugin code does not port, and 12 Claude skills are symlinked into it, so sharing a repo would couple their failures.
- Plugin as the distribution vehicle. It cannot carry rules, config or `AGENTS.md`.
