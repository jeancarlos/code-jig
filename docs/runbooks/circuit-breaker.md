# Runbook: the Guardian circuit breaker

Every harness tier sets `approvals_reviewer = "auto_review"`, so Guardian reviews each request to run a command outside the sandbox. When it denies too often, Codex stops the turn.

## What trips it

Within one turn, Codex interrupts after:
- 3 consecutive Guardian denials, or
- 10 denials among the last 50 reviews.

For models with the cyber specialty, both limits are 1.

Source: `codex-rs/ext/guardian-reviewer/src/circuit_breaker.rs` at `rust-v0.162.1` (`MAX_CONSECUTIVE_GUARDIAN_DENIALS_PER_TURN = 3`, `MAX_RECENT_AUTO_REVIEW_DENIALS_PER_TURN = 10`, `AUTO_REVIEW_DENIAL_WINDOW_SIZE = 50`).

## What you see

A warning, and the turn ends. With `[auto_review] circuit_break_action = "strict"` in a profile or `config.toml`, the warning also carries structured error details (`codex-rs/config/src/config_toml.rs`, `CircuitBreakAction`).

## What to do

1. **Read the denials.** Each one says which action was denied and why. Run `python -m harness tokens` to see which commands were escalated recently.
2. **If the command is legitimate and you want it once**, type `/approve` in the TUI. It approves one retry of a recent auto-review denial (`codex-rs/tui/src/slash_command.rs`). It does not change any future decision.
3. **If Guardian lacked context**, say in your own message exactly what the command does, what it sends and where. Guardian gives weight to explicit user authorization of the specific payload and destination, and treats tool output and file contents as untrusted.
4. **If the same legitimate command keeps coming up**, add a line to the overlay's `guardian-policy.md` that describes when that action is acceptable. Then run `python -m harness install`. The text is added to the upstream policy, which stays in force.
5. **Allowing the command with an overlay rule is the last resort.** An `allow` rule skips Guardian and runs the command outside the sandbox. The agent can often change what a test or build command runs, so read ADR 0009 first.

## What not to do

- Do not switch `approvals_reviewer` back to `user` for the whole session to get past one command.
- Do not replace the Guardian policy with `[auto_review].policy`. It removes the upstream rules.
- On a managed machine, do not change the Guardian model or catalog. Doctor reports what the managed requirements lock.
