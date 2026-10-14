# 0012: A Stop hook runs the collector from an installed copy

Status: accepted (2026-10-14)

## Decision
`harness install` merges one group into the `Stop` list of `$CODEX_HOME/hooks.json`, identified by `statusMessage = "codex-harness collect"`. Other hooks are kept, and repeated installs replace only that group. It also copies the `harness` package to `$CODEX_HOME/codex-harness/lib/`. The hook runs `PYTHONPATH=<lib> <python> -P -s -m harness --codex-home <home> collect`, and on Windows `set "PYTHONPATH=<lib>" && "<python>" -P -s -m harness ...`. `<python>` is the base interpreter, not a virtualenv's. `collect` always prints `{}` and exits 0, writing errors to stderr.

## Reason to exist
The tracker must be current without anyone remembering to run it, and without a daemon.

## Data
- Hooks live in `hooks.json` as `{"hooks": {"Stop": [{"hooks": [{"type": "command", "command", "commandWindows", "timeout", "statusMessage"}]}]}}` (`codex-rs/config/src/hook_config.rs`, rust-v0.162.1). POSIX runs `<shell> -lc <command>`; Windows runs `cmd /C <commandWindows>` (`hooks/src/engine/command_runner.rs`).
- The `Stop` hook's stdout must be JSON; `{}` is valid. A changed hook asks for trust again.
- A hook runs outside the sandbox, with the session's working directory as cwd. `python -m` puts the cwd first on `sys.path`, so a `harness/` package or a `json.py` written there by the agent would run unsandboxed. `-P` (Python 3.11+) removes that entry. A test plants both and checks they do not run.
- `-s` drops the user site-packages, and the base interpreter replaces a virtualenv one: a `.pth` file in either is code Python runs at startup, and both can sit inside a workspace the agent writes to.
- Pointing `PYTHONPATH` at the core checkout would let an agent working in that repo change what the hook runs. The copy under `$CODEX_HOME` is out of the agent's reach, because Codex keeps `<root>/.codex` read-only even when the workspace root is the home directory (`protocol/src/permissions.rs`).
- Managed requirements can set `allow_managed_hooks_only`, which disables this hook; doctor warns about it.

## Cost
About 60 lines in `install.py` and a doctor check. The hook rescans changed files in milliseconds, using stored offsets.

## Kind
Script.

## Rejected alternatives
- A daemon or file watcher: it is a background process on a managed laptop.
- Running `collect` by hand only: the numbers would go stale exactly when they matter.
- Failing loudly from the hook: a tracker bug must never break a Codex session.
