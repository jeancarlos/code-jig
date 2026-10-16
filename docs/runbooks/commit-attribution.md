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

Where the account setting cannot be changed, the code-jig git gate removes the lines before they reach a commit. Enable it in `overlay.toml`:

```toml
git_gate = true
prose_gate = true     # optional, see below
push_cleanup = false  # optional, on by default with git_gate, see below
```

`code-jig install` writes the gate to `~/.local/share/code-jig/git-hooks/` and sets `git config --global core.hooksPath` to it, but only when that setting is unset or already points there; otherwise it prints the command to switch and changes nothing. Every repo's own `.git/hooks` still run: each gate hook calls the repo hook of the same name after its own work, so git-lfs and similar hooks keep working. A repo that sets its own `core.hooksPath` (husky, for example) bypasses the gate; `code-jig doctor` run inside it says so.

| Hook | What it does |
|---|---|
| `commit-msg` | Removes invisible Unicode (zero-width characters and bidi controls; no-break spaces become spaces) and the attribution lines listed under "What counts as attribution"; turns em and en dashes into `-`. Never blocks. |
| `pre-commit` | Removes invisible Unicode (zero-width, bidi controls; no-break spaces become spaces) from staged text files, in the index and the working tree, and turns dashes into `-` in prose files. With `prose_gate`, refuses the commit when it comes from an agent session and stages human-facing prose. |
| `pre-push` | When commits by you that are about to be pushed still carry attribution or invisible characters in the message, cleans them (see "Cleanup on push") and refuses this push; run the same push again. Where it cannot clean them, it refuses and points at `code-jig scrub`. Then, when `git config codejig.testCommand "<command>"` is set (local, global or included), runs it from the repo top level and refuses the push if it exits non-zero. `CODE_JIG_SKIP_TESTS=1` skips the run for an emergency. The command also runs for delete-only pushes and has no timeout. |

"You" is `git config user.email` plus every `git config --global --add codejig.email <address>`, for older addresses of yours.

### Cleanup on push

With `push_cleanup` on (the default once `git_gate = true`), the pre-push hook rewrites the messages of the outgoing commits on the branch you push, with the same checks as `code-jig scrub`: trees, authors, committers and dates stay the same, a backup bundle goes in the git directory, and the branch is put back if a check fails. It touches only that branch and only commits that no remote-tracking branch (`refs/remotes/*`) already contains. Git has already chosen what to send by the time the hook runs, so the hook refuses that push and prints `run the same push again`; the second push sends the cleaned commits.

It falls back to the plain refusal, which points at `code-jig scrub`, when you push a tag or a commit by SHA instead of a local branch (`git push origin HEAD` counts as the checked-out branch), when a commit to clean is already on a remote-tracking branch, when the commits to rewrite include one by someone else or a signed commit, or when a rebase that moves that branch (as the branch being rebased or through `--update-refs`) or a `git am` on it is in progress in any worktree. A push of several branches is cleaned all together or not at all. Tags are not moved: a tag that points at a cleaned commit still points at the original, so a `--follow-tags` push that sends it is refused and needs `code-jig scrub`. Backup bundles go in the repo's common git directory, so removing a linked worktree keeps them. To turn it off everywhere, set `push_cleanup = false` in `overlay.toml` and run `code-jig install`. For one repo, `git config codejig.pushCleanup false` (or `true`) wins over the overlay.

### What counts as attribution

One remover serves the commit-msg hook, `code-jig scrub` and the watermark hook for files, so all three agree. It matches whole lines, case-insensitively, and covers Codex, Claude Code, Antigravity and Gemini, and VS Code Copilot, plus Cursor, Devin and Aider:

- `Co-authored-by:` lines that carry a tool signal: an address at anthropic.com, openai.com, cursor.com, cognition.ai, cognition-labs.com or aider.chat; a name containing `[bot]` (copilot-swe-agent[bot], google-labs-jules[bot], devin-ai-integration[bot] and the like); a name that is only a tool name (Claude, Codex, ChatGPT, GPT-5, Copilot, GitHub Copilot, Gemini, Antigravity, Cursor Agent, Aider, Devin AI, Jules) optionally followed by model or product words such as Code, Opus, Sonnet, Pro or a version number; or the words "an AI".
- `Generated with` or `Generated by` immediately followed by a tool name, optionally in a Markdown link bracket, such as `Generated with [Claude Code](...)` or `Generated by Copilot`.
- `Made with Cursor`, `Claude-Session:`, robot-emoji `Generated` lines, and lines starting with `ai-assisted` or `ai-generated`.

A person who merely shares a name with a tool stays: `Co-authored-by: Claude Monet <claude@example.com>`, `Jules Verne` and `Devin Smith <devin@gmail.com>` are kept. So does prose that only mentions a tool, like "fix the cursor position" or "Generated with the cursor position helper".

### The prose gate

An agent session is a commit run with `CODEX_THREAD_ID` (Codex sets it on every command) or `CLAUDECODE` (Claude Code) in the environment. Prose is `README*`, `CHANGELOG*`, `CHANGES*`, `HISTORY*`, `CONTRIBUTING*`, and `.md`, `.mdx`, `.markdown`, `.rst`, `.adoc` files, except `AGENTS.md`, `CLAUDE.md`, `SKILL.md` and anything under a `spec/` or `specs/` folder. The refusal tells the agent to unstage those files and commit the rest; you review and commit the prose yourself. In a repo where agents may commit prose, run `git config codejig.allowProse true` there. Codex keeps `.git` read-only inside its sandbox, so the agent cannot set that itself without an escalation Guardian reviews.

The gate can be bypassed with `git commit --no-verify` or by unsetting the variables; Guardian sees those commands, and the overlay's `guardian-policy.md` can call them out as high risk.

## Remove it from history: code-jig scrub

```sh
code-jig scrub --dry-run      # list your commits that carry attribution or invisible characters
code-jig scrub                # rewrite them, message only
```

It also removes invisible characters from your commit messages. It rewrites local branches and tags with git's own `fast-export` and `fast-import` (no extra tools), touches only commits by you, checks that every tree, author, committer and date is unchanged and restores every ref if not, and keeps a backup bundle in the git directory. The same history gives the same new SHAs on every clone. It never pushes: it prints one `git push --force-with-lease=<branch>:<old sha> ...` command per branch, so a push fails if someone pushed meanwhile. Other clones then run `git fetch` and `git reset --keep origin/<branch>`. The `remove-ai-attribution` skill walks an agent through it with your approval at each step.

Old commits stay reachable by SHA on the server until it garbage-collects them; on most hosts that needs the administrator.
