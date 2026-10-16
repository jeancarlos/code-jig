# Runbook: upgrading, rolling back, uninstalling

`install` copies what the hooks need into `~/.local/share/code-jig/lib/` (`%LOCALAPPDATA%\code-jig\lib\` on Windows) and writes the rest into `$CODEX_HOME`. The hooks run that copy, not the checkout, so a core change does nothing until the next `install`.

## Upgrade the core

If you installed with the bootstrap (a release install):

1. Set `core_version = "vX.Y.Z"` in the overlay's `overlay.toml`, then run `bootstrap.py` again (the same command you used to install). If the bootstrap made the overlay for you (`~/code-jig-overlay`, first line `# written by code-jig bootstrap`, no `.git`), you can run it with `--version latest` or `--version vX.Y.Z` instead, and it rewrites the pin.
2. The bootstrap downloads the new version folder, runs `install`, points the launcher at it and runs `doctor`. Fix every FAIL before the next session.
3. Without the web: download the newer `code-jig.zip` and `SHA256SUMS` from the release page and run `bootstrap.py --zip code-jig.zip` with the same overlay. A zip older than the installed version is refused unless `--version` names the zip's version (an explicit downgrade). `--github` makes a normal run use github.com only.
4. An overlay that is a git repository, or that you wrote yourself, is never rewritten. `--version` with a different tag is refused there; edit `core_version` yourself.

If you work from a checkout:

1. Get the new tag (`git fetch --tags && git checkout vX.Y.Z`, or download its archive).
2. Set `core_version = "vX.Y.Z"` in the overlay's `overlay.toml`.
3. `install`, then `doctor`. Fix every FAIL before the next session.

## When Codex updates

Codex updates on its own schedule. After an update:

1. Run `doctor`. `codex keys` FAIL means the new Codex dropped or renamed a setting the pack writes; the rest of the pack still works, but that setting is ignored.
2. Run `code-jig tokens`. A sudden `rollout lines quarantined` count means the session file format changed and the tracker is missing turns.
3. Report either one as an issue with both versions (`codex --version`, the core tag), then check for a newer core tag.

## Roll back the core

On a release install, set `core_version` back to the older tag and run the bootstrap again (or pass `--version vX.Y.Z` for a bootstrap-made overlay). Old version folders are kept, so a folder that is still there is reused without a download, after its digest is checked. The launcher moves back to it. Releases before v0.11.0 have no zip, so you cannot roll back past v0.11.0 this way.

From a checkout, check out the previous tag, set `core_version` back, run `install`. Generated files are rewritten in place. Core skills that the older version does not ship are removed, unless you edited them by hand, in which case `install` leaves them and warns. Rules come from the overlay, so a core rollback does not change them.

The tracker database survives a rollback: newer versions only add tables, so an older `Stop` hook keeps writing to it. Those tables (exit codes, skill reads, Guardian outcomes) stop updating until you upgrade again and run `collect --rescan`.

## What install touches

| Path | Notes |
|---|---|
| `$CODEX_HOME/AGENTS.md` | Generated. A hand-written file there is moved to `AGENTS.md.bak-<timestamp>` first. |
| `$CODEX_HOME/<tier>.config.toml` | One per tier. Same backup rule. |
| `$CODEX_HOME/rules/code-jig-*.rules` | From the overlay's `rules/`. `default.rules` is never touched. |
| `$CODEX_HOME/hooks.json` | The `Stop` entry with status `code-jig collect` is added or replaced; other hooks are kept. The previous file is copied to `hooks.json.bak-<timestamp>`. |
| `~/.local/share/code-jig/lib/` | The copy of code-jig the hooks run. |
| `~/.local/share/code-jig/usage.sqlite3` | Tracker data. Delete it to start counting from scratch; `collect --rescan` rebuilds it from the session files. |
| `~/.local/share/code-jig/vX.Y.Z/` (`%LOCALAPPDATA%\code-jig\vX.Y.Z\`) | Release installs only. One folder per version, kept after an upgrade. Delete the ones you no longer need. |
| `~/.local/bin/code-jig` and `cjig` (`%LOCALAPPDATA%\code-jig\bin\code-jig.cmd` and `cjig.cmd`) | Release installs only. The launcher, written after `install` succeeds. The bootstrap does not replace a file there that it did not write. |
| `~/code-jig-overlay` | Only when the bootstrap created it because you gave no overlay. |
| `~/.agents/skills/<name>/` | Core and overlay skills, each with a `.code-jig` marker. A skill already there under the same name is moved to `~/.agents/skills-backup/`. |

`config.toml` is never edited.

## Uninstall

There is no uninstall command. To remove the pack:

1. Delete `$CODEX_HOME/AGENTS.md`, the four `<tier>.config.toml` files, `$CODEX_HOME/rules/code-jig-*.rules` and `~/.local/share/code-jig/`.
2. Remove the `Stop` entry whose `statusMessage` is `code-jig collect` from `hooks.json`, or restore the oldest `hooks.json.bak-*`.
3. Delete each skill directory in `~/.agents/skills/` that holds a `.code-jig` file.
4. Move back anything you want from `~/.agents/skills-backup/` and from `*.bak-*` files.
5. On a release install, delete the version folders in `~/.local/share/code-jig/` (`%LOCALAPPDATA%\code-jig\`) and the launchers `~/.local/bin/code-jig` and `cjig` (`.cmd` files on Windows). Delete `~/code-jig-overlay` only if you want to lose your overlay.
6. `codex plugin remove superpowers@openai-curated-remote` if you added it.
