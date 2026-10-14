# 0009: No core allow rules

Status: accepted (2026-10-14)

## Decision
The core ships no exec-policy rules. The overlay may ship `rules/*.rules`; `harness install` copies them to `$CODEX_HOME/rules/codex-harness-<name>.rules`, removes copies whose source left the overlay, and never touches `rules/default.rules` or any other file. The example overlay rule is `forbidden` (force push), not `allow`.

## Reason to exist
The original design had a core allow-list of read-only commands to keep them away from Guardian. The source shows it saves nothing and opens a sandbox escape.

## Data
- An `allow` rule runs the command outside the sandbox: `Decision::Allow` sets `bypass_sandbox` (`codex-rs/core/src/exec_policy.rs`, rust-v0.162.1).
- With `on-request` approval and a restricted sandbox, a command that does not ask for escalation already runs without any review (same file). Read-only commands never reached Guardian.
- `git status` runs the program in `core.fsmonitor` from the repository config, and `rg --pre` runs any program. The agent can write both inside the sandbox, so allowing them hands it unsandboxed execution.
- `rules/default.rules` is where Codex writes the user's own "always allow" choices.
- Rule files validate their `match` and `not_match` examples at load; a bad example fails the load (bench, `codex execpolicy check`).

## Cost
Install copies and prunes files; CI checks the example with `codex execpolicy check`.

## Kind
Static.

## Rejected alternatives
- The read-only allow-list above.
- Allowing test or build commands in the core: the agent can edit what those commands run (test files, package scripts, Makefiles), so each allow is a per-repo trust decision for the overlay. Which commands actually reach Guardian is measured in step 3 before any allow rule is recommended.
