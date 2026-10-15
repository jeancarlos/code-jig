# Runbook: Codex commit and PR attribution

Codex can add a `Co-authored-by: Codex <noreply@openai.com>` trailer to commits it writes and a `Generated with [Codex](https://openai.com/codex/).` line to pull request bodies.

## How it is decided

Since the `codex_git_commit` feature and the `commit_attribution` config key were removed, there is no local setting. At the start of a thread Codex asks the ChatGPT backend for the account's `commit_attribution_enabled` setting and, when it is on, adds a developer instruction telling the model to attribute (`codex-rs/ext/git-attribution/`, rust-v0.162.1). With API-key login it is always off. If the setting cannot be fetched, it is treated as off.

That instruction says to ignore earlier instructions that disable attribution, so a line in AGENTS.md does not reliably override it.

## Turn it off

1. In your ChatGPT account's Codex settings, turn commit attribution off. On a workspace plan an administrator may control it.
2. Start a new thread; the setting is cached per thread.

## Check it

A commit Codex made:

```sh
git log -1 --format=%B | grep -i "co-authored-by: codex"
```

Any matches across a branch before you push:

```sh
git log --format='%h %B' main..HEAD | grep -i "co-authored-by: codex\|generated with \[codex\]"
```

## Strip it at the source: the git gate

Where the account setting cannot be changed, the harness git gate removes the lines before they reach a commit. Enable it in `overlay.toml`:

```toml
git_gate = true
prose_gate = true   # optional, see below
```

`harness install` writes the gate to `$CODEX_HOME/codex-harness/git-hooks/` and sets `git config --global core.hooksPath` to it, but only when that setting is unset or already points there; otherwise it prints the command to switch and changes nothing. Every repo's own `.git/hooks` still run: each gate hook calls the repo hook of the same name after its own work, so git-lfs and similar hooks keep working. A repo that sets its own `core.hooksPath` (husky, for example) bypasses the gate; `harness doctor` run inside it says so.

| Hook | What it does |
|---|---|
| `commit-msg` | Removes `Co-authored-by:` lines naming Codex, Claude, ChatGPT or an AI, `Generated with` lines naming them, `Claude-Session:` and robot-emoji lines; turns em and en dashes into `-`. Never blocks. |
| `pre-commit` | Removes invisible Unicode (zero-width, bidi controls; no-break spaces become spaces) from staged text files, in the index and the working tree, and turns dashes into `-` in prose files. With `prose_gate`, refuses the commit when it comes from an agent session and stages human-facing prose. |
| `pre-push` | Refuses to push commits by you whose message still carries attribution, and points at `harness scrub`. |

"You" is `git config user.email` plus every `git config --global --add codexharness.email <address>`, for older addresses of yours.

### The prose gate

An agent session is a commit run with `CODEX_THREAD_ID` (Codex sets it on every command) or `CLAUDECODE` (Claude Code) in the environment. Prose is `README*`, `CHANGELOG*`, `CHANGES*`, `HISTORY*`, `CONTRIBUTING*`, and `.md`, `.mdx`, `.markdown`, `.rst`, `.adoc` files, except `AGENTS.md`, `CLAUDE.md`, `SKILL.md` and anything under a `spec/` or `specs/` folder. The refusal tells the agent to unstage those files and commit the rest; you review and commit the prose yourself. In a repo where agents may commit prose, run `git config codexharness.allowProse true` there. Codex keeps `.git` read-only inside its sandbox, so the agent cannot set that itself without an escalation Guardian reviews.

The gate can be bypassed with `git commit --no-verify` or by unsetting the variables; Guardian sees those commands, and the overlay's `guardian-policy.md` can call them out as high risk.

## Remove it from history: harness scrub

```sh
harness scrub --dry-run      # list your commits that carry attribution
harness scrub                # rewrite them, message only
```

It rewrites local branches and tags with git's own `fast-export` and `fast-import` (no extra tools), touches only commits by you, checks that every tree, author, committer and date is unchanged and restores every ref if not, and keeps a backup bundle in the git directory. The same history gives the same new SHAs on every clone. It never pushes: it prints one `git push --force-with-lease=<branch>:<old sha> ...` command per branch, so a push fails if someone pushed meanwhile. Other clones then run `git fetch` and `git reset --keep origin/<branch>`. The `remove-ai-attribution` skill walks an agent through it with your approval at each step.

Old commits stay reachable by SHA on the server until it garbage-collects them; on most hosts that needs the administrator.
