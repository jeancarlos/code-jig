# 0028: code-jig, the rename and the adapter design

Status: accepted (2026-10-16)

## Decision

The project is renamed from its Codex-only name to code-jig. This release changes names and paths only. Codex output for an unchanged overlay differs from the previous release only where a name or path changed.

- **Names.** Repo `jeancarlos/code-jig` (GitHub redirects the old URL), overlay repo `code-jig-overlay`, package `codejig/` run as `python -m codejig`, commands `code-jig` and `cjig`, env vars `CODE_JIG_OVERLAY` and `CODE_JIG_SKILLS_DIR`, git config section `codejig` (`codejig.allowProse`, `codejig.email`), status messages and file prefixes `code-jig`, release asset `code-jig.zip`, a preview page at `code-jig.jeansouza.dev`. The install commands download `bootstrap.py` and the zip from the GitHub release only, so a network that blocks the domain can still install; the Worker no longer serves `/setup` or `/v/<tag>/<file>` and counts nothing. The bootstrap default overlay folder is `~/code-jig-overlay`.
- **Why not `harness` or `jig`.** The Harness.io CLI installs `harness` into `~/.local/bin`, and Arch ships `/usr/bin/jig`. `code-jig` and `cjig` were checked free on PyPI, npm, crates, Homebrew, Arch, the AUR, Debian, nixpkgs, Scoop and dnf on 2026-10-16. winget was not checked.
- **State directory.** `$XDG_DATA_HOME/code-jig`, or `~/.local/share/code-jig` (Linux, macOS), and `%LOCALAPPDATA%\code-jig` (Windows). It holds `usage.sqlite3`, `lib/` and `git-hooks/`. This is the folder the bootstrap already used for release versions, so there is one data folder. `lib/`, the copy of the code the hooks run, lives here and not under `$CODEX_HOME` because the git hooks and the Claude Code watermark hook import it and none of it belongs to one tool.
- **No runtime fallbacks.** Nothing at run time reads the old env vars, the old git section, the old state directory or the old command. Only `codejig/migrate.py` names them, and a test keeps every other file free of the old names. A machine that skips the rename release cannot migrate.
- **`migrate` is deprecated on arrival.** `code-jig migrate [--dry-run] [repo...]` prints `code-jig migrate is deprecated and will be removed in the next release` first on every run and is deleted in the next release, once it has run on every machine with old state. It is idempotent and prints each action. It moves the tracker database, unsets the old `core.hooksPath` (the `install` it runs sets the new one when `git_gate = true` in the overlay), copies the git config keys, removes the files the old version generated, renames skill sidecars and links, and writes the new launchers. It does not rename the repo or move checkouts; that is done by hand.
  - It also removes the old status-message entries from `~/.claude/settings.json`, which goes beyond the design's step list.
  - Before it changes anything, it checks that `install` would succeed. It moves the database and copies the git keys first, and unsets the old `core.hooksPath` only when both went through. Any refusal or failure stops the run there, so the database never splits between two places and the old git gate stays in place. It never deletes the old hooks while `core.hooksPath` still points at them. If `install` fails afterwards with `git_gate = true`, it says the gate is off, and a rerun is not done until the new gate is active. A rerun finishes the rest.
  - `code-jig doctor` reports old state that is still pending as a FAIL that says to run `code-jig migrate`. Only `migrate` names old identifiers.
- **Tracker.** The `agent` column arrives in phase 2 with default `codex`, which tags the migrated rows. `migrate` only moves the database.
- **Any machine, any tool.** A machine may run Codex, Claude Code or both. Nothing assumes one tool per machine.
- **Adapters, phase 2.** Phase 1 produces Codex output only. In phase 2 the shared source stays Claude format, and each target gets one TOML manifest that maps it, with an optional overlay `.py` for what a manifest cannot say and a warning for every gap a target cannot express. The design note for this rename has the details. The `PostToolUse` matcher fix is phase 2 too.

## Context

The old command name collided with another tool on the same `PATH`, and the project had grown past one agent: the skills, the git gate and the watermark hook already serve Claude Code. A name that says Codex stopped being true.

A rename touches state that lives outside the repo: a database, a global git config, a hooks path, skill links in two tools and shell launchers. Reading both names at run time would leave every code path with two answers and no date to remove either. A one-shot command that is deleted after use keeps the old names in one file and one release.

## Consequences

- The release after this one deletes `codejig/migrate.py`, its tests and its runbook, and the doctor check for old state.
- ADRs 0001 to 0027 keep their text and the old names. Read them with the mapping above.
- A machine that installed the previous release must run `code-jig migrate` before `doctor` passes; see [the runbook](../runbooks/migrate-to-code-jig.md).
