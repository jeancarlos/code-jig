# 0013: Skills are copied into the Codex user skills folder

Status: accepted (2026-10-14)

## Decision
The core ships four skills in `skills/`: `cross-review`, `web-consensus`, `grilling` and `improve`. An overlay may add its own in `<overlay>/skills/`. A name used by both is an error. `harness install` copies each skill to `~/.agents/skills/<name>/` with a `.codex-harness` sidecar holding a sha256 of the copied tree. A directory is only replaced or pruned while its sidecar still matches; a user's own directory with the same name is moved to a timestamped backup in `~/.agents/skills-backup/`, outside the skills root so Codex stops loading it. superpowers is not copied: doctor checks `config.toml` for `[plugins."superpowers@..."]` and otherwise prints `codex plugin add superpowers@openai-curated`. Doctor's prompt probe checks that every installed skill appears in Codex's skills list.

## Reason to exist
These are the workflows used most on the bench (planning, cross-model review, sourced research, decision interviews), plus the one that lets the harness improve itself without leaking corporate knowledge.

## Data
- Codex reads user skills from `~/.agents/skills`. `$CODEX_HOME/skills` is "deprecated ... kept for backward compatibility" (`codex-rs/ext/skills/src/host_roots.rs`, rust-v0.162.1).
- `SKILL.md` must start with a `---` frontmatter line (`codex-rs/skills/src/parser.rs`), so the ownership marker cannot go in the file itself.
- Codex lists loaded skills in the prompt as `- <name>: <description> (file: ...)` (bench, `debug prompt-input`).
- superpowers 6.4.2 is published as `superpowers@openai-curated` and installs non-interactively with `codex plugin add` (bench).

## Cost
About 50 lines in `install.py`, four Markdown files, two doctor checks.

## Kind
Static (skills) and script (install, checks).

## Rejected alternatives
- Symlinks: they need extra rights on Windows, and `doctor` could not tell an edited skill from ours.
- Installing superpowers automatically: it is third-party code from the network, and managed config can restrict plugin sources. The user runs one command.
- Vendoring the original skill texts: they carried personal and infrastructure details. The core texts are generic rewrites.
