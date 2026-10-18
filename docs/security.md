# Security requirements

What you can and cannot expect from code-jig. The reasons these hold are in [assurance-case.md](assurance-case.md); how to report a problem is in [SECURITY.md](../SECURITY.md).

## What you can expect

- It writes only where it says it writes: the Codex home, the skills directory, the Claude Code settings when present, its own SQLite store, and, for the commands that edit files, the paths the agent just wrote inside the working directory.
- It does not overwrite a file it did not generate. Generated files carry a `sha256` stamp; any other file is moved aside to a `.bak-` copy first. A symlink, hard link or swapped path is refused, not followed.
- It runs no network calls except two you start: `check-sources` (public http and https addresses only, redirects included) and `humanize --rewrite` (https, or http to this machine only, never following a redirect, and only after you confirm or pass `--yes`).
- It verifies TLS certificates with the Python defaults and never disables verification.
- It never runs user text through a shell, except the test command you configure for the git gate, which is yours.
- Telemetry opt-outs are set on every tool it runs, and the core never downloads a tool at run time.
- Your usage data stays in a local database. Nothing is sent anywhere.
- The wheel you install is the one CI built from the tag. You can verify it with `gh attestation verify` and `cosign verify-blob`, and `doctor` detects edits made after installation.
- Hooks fail open on their own errors, so a bug in a hook never blocks your agent.

## What you cannot expect

- It is not a sandbox. Codex's sandbox and Guardian make the allow and deny decisions; code-jig only configures them. An `allow` rule in your overlay runs a command outside the sandbox, and the agent can edit what a test or build command runs.
- It does not protect against an attacker who already controls your account, your overlay or the machine.
- The cross-review reviewer keeps a read-only shell, so an instruction injected into the diff could read local files into that model's context. It cannot write or escalate.
- `humanize --rewrite` sends the flagged comment text to the gateway you chose, with your key. Choose a gateway you trust.
- It does not hide secrets in files the agent reads. Use a secret scanner (`code-jig analyze` runs gitleaks).
- Only the latest release gets security fixes.
