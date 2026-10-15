# 0024: An opt-in git gate for attribution, invisible characters and agent-written prose

Status: accepted (2026-10-15)

## Decision

With `git_gate = true` in `overlay.toml`, `harness install` writes one POSIX shell hook per git hook name to `$CODEX_HOME/codex-harness/git-hooks/` and sets the global `core.hooksPath` to that folder, only when it is unset or already points there. Turning the flag off unsets it again, only if it still points there. Three hooks run `python -m harness git-hook <name>` from the installed copy of the harness, with `-P -s` as the `Stop` hook does (ADR 0012):

- `commit-msg` removes attribution lines (`ATTRIBUTION_LINES`) and turns em and en dashes into `-`;
- `pre-commit` removes invisible characters from staged text files, in the index and the working tree, and dashes in prose files; with `prose_gate = true` it refuses a commit that comes from an agent session (`CODEX_THREAD_ID` or `CLAUDECODE` set) and stages human-facing prose, unless the repo has `codexharness.allowProse = true`;
- `pre-push` refuses the user's outgoing commits whose message still carries attribution, and points at `harness scrub` (0022).

Every hook then runs the repository's own hook of the same name from `$(git rev-parse --git-common-dir)/hooks`, so repository and tool hooks keep working. Doctor reports whether the gate is active and whether the current repository overrides it.

## Context

The personal setup ran an equivalent gate (`ai-gate.py`) from `~/.config/git/hooks`, with personal addresses hard-coded and a dependency on a separate Unicode library. The user asked for it, and for the rule that agents do not commit human-facing prose they wrote, to be part of the harness. On a managed machine it is the only way to stop the Codex co-author line when an administrator keeps attribution on.

## Data

- Codex injects `CODEX_THREAD_ID` into the environment of every command it runs (`core/src/exec_env.rs`, rust-v0.162.1); Claude Code sets `CLAUDECODE`.
- Codex keeps `.git` read-only inside the sandbox (`protocol/src/permissions.rs`, the protected `.git` subpath), so an agent commit escalates to Guardian, and the agent cannot set `codexharness.allowProse` in the repository without that review.
- A global `core.hooksPath` replaces `.git/hooks` for every repository; chaining to the repository's hooks is what keeps git-lfs and project hooks alive. A repository-level `core.hooksPath` (husky and similar) wins over the global one.
- Git for Windows runs hooks with its bundled `sh`, so the same POSIX scripts serve both systems; paths are written with forward slashes.
- The gate's own failures (git missing, unreadable file) print a note and let the commit through: a gate bug must not block work. Only the prose and push refusals exit 1.

- Staged files are read from one `git diff --cached --raw -z --no-renames --no-abbrev`, never with a path passed to `ls-files`: a file named like a pathspec (`a?`) matched another file there and the gate wrote that file's content into its index entry. `--no-renames` makes a rename into `README.md` an addition, so it is cleaned and gated (security review, v0.9.1).
- `codexharness.allowProse` is read with `git config --local`, which ignores `git -c` and `GIT_CONFIG_PARAMETERS`; a plain read let `git -c codexharness.allowProse=true commit` pass the gate.

## Cost

About 170 lines, sixteen tests including a real commit through the generated hooks, two overlay flags, one doctor check.

## Rejected

- On by default: it changes git behaviour for every repository on the machine.
- Detecting AI-written prose by content: no reliable signal; the session environment is a fact.
- Refusing invisible characters instead of removing them: the original gate replaced them silently, and the user kept that behaviour.
- Checking file contents again at push: the pre-commit fix already ran on every commit made through the gate.
