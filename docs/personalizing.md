# Personalizing

## Core vs overlay
Core is shared and pinned. The overlay is a separate directory with fixed slots:
- `overlay.toml`: `core_version`, `core_writable`.
- `profiles.toml`: one model ID per tier (`default`, `deep`, `bulk`, `review`). `doctor` lists the models your account has.
- `AGENTS.overlay.md`: appended to the core rules.
- `guardian-policy.md`: added to the upstream Guardian policy, never replacing it.
- `rules/*.rules`: Codex exec-policy rules. An `allow` rule runs the command outside the sandbox and skips Guardian, and the agent can edit what a test or build command runs, so only allow what you would run unsupervised in that repo. `forbidden` rules are always safe to add.

- `skills/<name>/SKILL.md`: your own skills, installed next to the core ones. A name the core already uses is an error.
- `knowledge/`: one fact per file, plus `knowledge/INDEX.md` with one line per fact. When the index exists, the generated `AGENTS.md` points Codex at it. Keep it at 150 lines or fewer; `doctor` warns past that. The `improve` skill maintains it. Pass it with `--overlay <dir>` or `CODEX_HARNESS_OVERLAY`.

## Private overlay
Keep your overlay in its own private repo. Never put it inside the core checkout. See `overlay-examples/personal`, and `overlay-examples/enterprise` for a locked-down machine.

## core_writable
`core_writable = false` means nothing may edit the core; `doctor` checks the core tree is unchanged. Set it to true only if you intend to change the core; the `improve` skill honours it.

## Pinning core_version
Pin `core_version` to a tag (for example v0.4.1). `doctor` reports `ok core pin: v0.4.1`, and FAILs a core that is not a git checkout.

## Clean-room rule
Contribute upstream only what you wrote without copying from private overlays or employer material. No corporate measurements anywhere in the core.

## Simulating a managed laptop
`bench/requirements.toml` is a guess at what an enterprise locks. Install it with `sudo install -D -m 644 bench/requirements.toml /etc/codex/requirements.toml`, remove it with `sudo rm /etc/codex/requirements.toml`. On a managed laptop, `doctor` shows how the real requirements differ from it.
