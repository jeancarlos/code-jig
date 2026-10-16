# Runbook: migrate a machine to code-jig

Run this once on every machine that had the previous, Codex-only version. `code-jig migrate` is deprecated and is removed in the next release, so a machine that skips this release cannot migrate. A machine with no old state has nothing to do.

## Steps

`code-jig` and `cjig` exist only after a bootstrap install or after `migrate` has run. On a checkout, run the module instead. `migrate` needs the overlay: pass `--overlay PATH` before the subcommand, or set `CODE_JIG_OVERLAY`. The old `CODEX_HARNESS_OVERLAY` is no longer read, so set the new one in your shell first.

1. Check you have Python 3.11 or newer and git; the install refuses without them. Get the new version, from a checkout of this repo or with the bootstrap (see the README). Close Codex and Claude Code, so nothing holds the tracker database. `install` may already have run; that is fine as long as it has not tracked any new sessions.
2. See what would change. On a checkout (Linux, macOS):

   ```sh
   PYTHONPATH=<checkout> python3 -m codejig --overlay <overlay> migrate --dry-run
   ```

   On Windows (PowerShell):

   ```powershell
   $env:PYTHONPATH = "<checkout>"; py -3 -m codejig --overlay <overlay> migrate --dry-run
   ```

   After a bootstrap install the launcher works: `code-jig --overlay <overlay> migrate --dry-run` (`code-jig.cmd` on Windows).
3. Run it without `--dry-run`, naming each repo that carries a repo-level `allowProse` setting. With no repo it uses the current one:

   ```sh
   PYTHONPATH=<checkout> python3 -m codejig --overlay <overlay> migrate ~/src/app ~/src/api
   ```

4. Check the result. The launcher now exists:

   ```sh
   code-jig --overlay <overlay> doctor
   ```

   `doctor` fails with `run code-jig migrate` while old state remains. Old git keys can also sit in a file your global config includes, and `migrate` does not touch those. Find them with:

   ```sh
   git config --show-origin --get-regexp codexharness
   ```

   `doctor` reports each one as `<key> in <file>: edit by hand`. Delete them from that file yourself.

## What it does

It prints `code-jig migrate is deprecated and will be removed in the next release` first, then each action. Before it changes anything, it checks that `install` would succeed with this overlay and these hook files. If not, it prints a `failed:` line and stops with nothing changed. Then it:

1. Moves the tracker database to `~/.local/share/code-jig/usage.sqlite3` (`%LOCALAPPDATA%\code-jig\usage.sqlite3`).
2. Copies the old git config keys (`email`, `allowProse`) to the `codejig` section and unsets the old ones.
3. Unsets the old global `core.hooksPath`. The `install` it runs sets the new one when `git_gate = true` in the overlay.
4. Removes the files the old version generated, including its hook entries in `~/.codex/hooks.json` and `~/.claude/settings.json`. It also removes the backups a bootstrap install made of those files and of old skill copies, but only when they are still unedited. Then it runs `install` to write the new ones.
5. Renames skill sidecars and replaces skill links that point into the old checkout with copies.
6. Writes the `code-jig` and `cjig` launchers. It deletes an old `harness` launcher only if it is the known one, and prints `left <path>: not a code-jig launcher` for any other `harness` file, which may belong to another tool.
7. Prints, without editing, shell files and config folders that still name the old env var or paths. Fix those by hand.

## When it refuses

Moving the database and copying the git keys run first. If either is refused or fails, `migrate` prints `skipped the remaining steps` and changes nothing else. The old `core.hooksPath` stays set, so the old git gate keeps working and the database never ends up in two places. If unsetting the old `core.hooksPath` fails, the rest is skipped the same way. While the global `core.hooksPath` still points at the old folder, `migrate` never deletes the old hooks or the code they run.

If `install` fails at the end, `migrate` prints `failed: code-jig install: ...`. When the overlay has `git_gate = true` and the new gate is not active yet, it also prints `failed: the git gate is off until code-jig install succeeds`. The next run does not report nothing to do until the new gate is active.

Fix the line it printed (usually a program that still has the database open) and run the same command again. It finishes the rest and then reports nothing to do.

If `install` ran before `migrate` and created a new, populated database, `migrate` refuses to overwrite it. Move the new database away and run again: `collect` rebuilds it from the rollouts.

## Not part of migrate

Renaming the GitHub repo, moving the checkouts to `~/PROJECTS/code-jig` and `~/PROJECTS/code-jig-overlay`, and updating remotes are done by hand. Do them before step 1 if you work from a checkout.
