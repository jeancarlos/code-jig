# Runbook: upgrading, rolling back, uninstalling

`install` copies everything it needs into `$CODEX_HOME`. The `Stop` hook runs that copy, not the checkout, so a core change does nothing until the next `install`.

## Upgrade the core

1. Get the new tag (`git fetch --tags && git checkout vX.Y.Z`, or download its archive).
2. Set `core_version = "vX.Y.Z"` in the overlay's `overlay.toml`.
3. `install`, then `doctor`. Fix every FAIL before the next session.

## When Codex updates

Codex updates on its own schedule. After an update:

1. Run `doctor`. `codex keys` FAIL means the new Codex dropped or renamed a setting the pack writes; the rest of the pack still works, but that setting is ignored.
2. Run `harness tokens`. A sudden `rollout lines quarantined` count means the session file format changed and the tracker is missing turns.
3. Report either one as an issue with both versions (`codex --version`, the core tag), then check for a newer core tag.

## Roll back the core

Check out the previous tag, set `core_version` back, run `install`. Generated files are rewritten in place. Core skills that the older version does not ship are removed, unless you edited them by hand, in which case `install` leaves them and warns. Rules come from the overlay, so a core rollback does not change them.

The tracker database survives a rollback: newer versions only add tables, so an older `Stop` hook keeps writing to it. Those tables (exit codes, skill reads, Guardian outcomes) stop updating until you upgrade again and run `collect --rescan`.

## What install touches

| Path | Notes |
|---|---|
| `$CODEX_HOME/AGENTS.md` | Generated. A hand-written file there is moved to `AGENTS.md.bak-<timestamp>` first. |
| `$CODEX_HOME/<tier>.config.toml` | One per tier. Same backup rule. |
| `$CODEX_HOME/rules/codex-harness-*.rules` | From the overlay's `rules/`. `default.rules` is never touched. |
| `$CODEX_HOME/hooks.json` | The `Stop` entry with status `codex-harness collect` is added or replaced; other hooks are kept. The previous file is copied to `hooks.json.bak-<timestamp>`. |
| `$CODEX_HOME/codex-harness/lib/` | The copy of the harness the hook runs. |
| `$CODEX_HOME/codex-harness/usage.sqlite3` | Tracker data. Delete it to start counting from scratch; `collect --rescan` rebuilds it from the session files. |
| `~/.agents/skills/<name>/` | Core and overlay skills, each with a `.codex-harness` marker. A skill already there under the same name is moved to `~/.agents/skills-backup/`. |

`config.toml` is never edited.

## Uninstall

There is no uninstall command. To remove the pack:

1. Delete `$CODEX_HOME/AGENTS.md`, the four `<tier>.config.toml` files, `$CODEX_HOME/rules/codex-harness-*.rules` and `$CODEX_HOME/codex-harness/`.
2. Remove the `Stop` entry whose `statusMessage` is `codex-harness collect` from `hooks.json`, or restore the oldest `hooks.json.bak-*`.
3. Delete each skill directory in `~/.agents/skills/` that holds a `.codex-harness` file.
4. Move back anything you want from `~/.agents/skills-backup/` and from `*.bak-*` files.
5. `codex plugin remove superpowers@openai-curated-remote` if you added it.
