# Runbook: migrate a machine to code-jig

Run this once on every machine that had the previous, Codex-only version. `code-jig migrate` is deprecated and is removed in the next release, so a machine that skips this release cannot migrate. A machine with no old state has nothing to do.

## Steps

1. Get the new version, from a checkout of this repo or with the bootstrap (see the README). Close Codex and Claude Code, so nothing holds the tracker database. `install` may already have run; that is fine as long as it has not tracked any new sessions.
2. See what would change:

   ```sh
   code-jig migrate --dry-run
   ```

   On Windows: `py -3 -m codejig migrate --dry-run` from the core folder.
3. Run it, naming each repo that carries a repo-level `allowProse` setting. With no repo it uses the current one:

   ```sh
   code-jig migrate ~/src/app ~/src/api
   ```

4. Check the result:

   ```sh
   code-jig doctor
   ```

   `doctor` fails with `run code-jig migrate` while old state remains.

## What it does

It prints `code-jig migrate is deprecated and will be removed in the next release` first, then each action. It:

1. Moves the tracker database to `~/.local/share/code-jig/usage.sqlite3` (`%LOCALAPPDATA%\code-jig\usage.sqlite3`).
2. Points global `core.hooksPath` at the new `git-hooks` folder.
3. Copies the old git config keys (`email`, `allowProse`) to the `codejig` section and unsets the old ones.
4. Removes the files the old version generated, including its hook entries in `~/.codex/hooks.json` and `~/.claude/settings.json`, then runs `install` to write the new ones.
5. Renames skill sidecars and replaces skill links that point into the old checkout with copies.
6. Writes the `code-jig` and `cjig` launchers and deletes the old `harness` launcher only if it is the known one.
7. Prints, without editing, shell files and config folders that still name the old env var or paths. Fix those by hand.

## When it refuses

A step that is refused or fails stops the ones after it, so the database never ends up in two places and the old git gate is never removed while it still works. Fix the line it printed (usually a program that still has the database open) and run the same command again. It finishes the rest and then reports nothing to do.

If `install` ran before `migrate` and created a new, populated database, `migrate` refuses to overwrite either one and says how to proceed.

## Not part of migrate

Renaming the GitHub repo, moving the checkouts to `~/PROJECTS/code-jig` and `~/PROJECTS/code-jig-overlay`, and updating remotes are done by hand. Do them before step 1 if you work from a checkout.
