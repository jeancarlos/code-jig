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

`code-jig install` writes the gate to `~/.local/share/code-jig/git-hooks/` and sets `git config --global core.hooksPath` to it, but only when that setting is unset or already points there; otherwise it prints the command to switch and changes nothing. Every repo's own `.git/hooks` still run: each gate hook calls the repo hook of the same name after its own work, so git-lfs and similar hooks keep working. A repo that sets its own `core.hooksPath` (husky, for example) bypasses the gate, because git then runs only that repo's hooks and the gate cannot refuse anything there. `code-jig doctor` run inside such a repo fails. Unset the repo's setting (`git config --local --unset core.hooksPath`) or have its hook manager call the gate's hook of the same name in `~/.local/share/code-jig/git-hooks/`.

| Hook | What it does |
|---|---|
| `commit-msg` | Removes invisible Unicode (zero-width characters and bidi controls; no-break spaces become spaces; joiners inside emoji and words stay) and the attribution lines listed under "What counts as attribution" from the closing trailer paragraphs (the subject and the body text are never touched); turns em and en dashes into `-`. |
| `pre-commit` | Removes invisible Unicode from staged files where it cannot be meant, in the index and the working tree: anywhere in prose files (`.md`, `.mdx`, `.markdown`, `.rst`, `.adoc`, `.txt`) and outside string literals in Python. Elsewhere (other code, data, Python that does not tokenize) it changes nothing: in an agent session it refuses the commit and lists each `file:line`, so the agent writes the character as an escape or deletes it; a human commit gets the list as a note. Turns dashes into `-` in prose files. With `prose_gate`, refuses the commit when it comes from an agent session and stages human-facing prose. |
| `pre-push` | When commits by you that are about to be pushed, merge commits included, still carry attribution or invisible characters in the message, cleans them (see "Cleanup on push") and refuses this push; run the same push again. Where it cannot clean them, it refuses and says which commits are locked (see "Commits already on a remote are locked") and how to fix the others. Then, when `git config codejig.testCommand "<command>"` is set (local, global or included), runs it from the repo top level and refuses the push if it exits non-zero. `CODE_JIG_SKIP_TESTS=1` skips the run for an emergency. The command also runs for delete-only pushes and has no timeout. It fails closed: when it cannot finish its checks (a git error, a shallow clone missing objects, no `user.email`), it refuses the push and says why. |

"You" is `git config user.email` plus every `git config --global --add codejig.email <address>`, for older addresses of yours.

### Cleanup on push

With `push_cleanup` on (the default once `git_gate = true`), the pre-push hook rewrites the messages of the outgoing commits on the branch you push, and checks the result: trees, authors, committers and dates stay the same, a backup bundle goes in the git directory, and the branch is put back if a check fails. It touches only that branch and only commits that no remote-tracking branch (`refs/remotes/*`) already contains. Git has already chosen what to send by the time the hook runs, so the hook refuses that push and prints `run the same push again`; the second push sends the cleaned commits.

It falls back to the plain refusal when you push a tag or a commit by SHA instead of a local branch (`git push origin HEAD` counts as the checked-out branch), when a commit to clean is already on a remote-tracking branch, when the commits to rewrite include one by someone else or a signed commit, or when a rebase that moves that branch (as the branch being rebased or through `--update-refs`) or a `git am` on it is in progress in any worktree. A push of several branches is cleaned all together or not at all. Tags are not moved: a tag that points at a cleaned commit still points at the original, so a `--follow-tags` push that sends it is refused until you move or delete the tag yourself. Backup bundles go in the repo's common git directory, so removing a linked worktree keeps them. To turn it off everywhere, set `push_cleanup = false` in `overlay.toml` and run `code-jig install`. For one repo, `git config codejig.pushCleanup false` (or `true`) wins over the overlay.

### What counts as attribution

One matcher serves the commit-msg hook, the pre-push check and the watermark hook for files, so they agree. Commit messages lose matching lines only in their closing trailer paragraphs; files never lose them, the watermark hook only reports them to the agent. It matches whole lines, case-insensitively, and covers Codex, Claude Code, Antigravity and Gemini, and VS Code Copilot, plus Cursor, Devin and Aider:

- `Co-authored-by:` lines that carry a tool signal: an address at anthropic.com, openai.com, cursor.com, cognition.ai, cognition-labs.com or aider.chat; a `[bot]` name that contains a tool name (copilot-swe-agent[bot], google-labs-jules[bot], devin-ai-integration[bot] and the like; dependabot[bot] and renovate[bot] stay); a name that is only a tool name (Claude, Codex, ChatGPT, GPT-5, Copilot, GitHub Copilot, Gemini, Antigravity, Cursor Agent, Aider, Devin AI, Jules) optionally followed by model or product words such as Code, Opus, Sonnet, Pro or a version number; or the words "an AI".
- `Generated with` or `Generated by` immediately followed by a tool name, optionally in a Markdown link bracket, such as `Generated with [Claude Code](...)` or `Generated by Copilot`.
- `Made with Cursor`, `Claude-Session:`, robot-emoji `Generated` lines, and lines that are only `AI-assisted` or `AI-generated`, or that trailer followed by `:` and a value.

A person who merely shares a name with a tool stays: `Co-authored-by: Claude Monet <claude@example.com>`, `Jules Verne` and `Devin Smith <devin@gmail.com>` are kept. So does prose that only mentions a tool, like "fix the cursor position" or "Generated with the cursor position helper", and a subject such as "AI-generated images are now rejected".

### The prose gate

An agent session is a commit run with `CODEX_THREAD_ID` (Codex sets it on every command) or `CLAUDECODE` (Claude Code) in the environment. Prose is `README*`, `CHANGELOG*`, `CHANGES*`, `HISTORY*`, `CONTRIBUTING*`, and `.md`, `.mdx`, `.markdown`, `.rst`, `.adoc` files, except `AGENTS.md`, `CLAUDE.md`, `SKILL.md` and anything under a `spec/` or `specs/` folder. The refusal tells the agent to unstage those files and commit the rest; you review and commit the prose yourself. In a repo where agents may commit prose, run `git config codejig.allowProse true` there. Codex keeps `.git` read-only inside its sandbox, so the agent cannot set that itself without an escalation Guardian reviews.

The gate can be bypassed with `git commit --no-verify` or by unsetting the variables; Guardian sees those commands, and the overlay's `guardian-policy.md` can call them out as high risk.

## Commits already on a remote are locked

code-jig edits only what has not left your machine: the message being written, staged files, and outgoing commits that no remote-tracking branch (`refs/remotes/*`) contains. A commit that any remote-tracking branch already contains is locked. The gate never rewrites it and lists it in the refusal as `[locked: already on a remote]`.

Fixing a locked commit rewrites shared history, so it is your call and a manual job:

1. `git rebase -i <sha>^`, mark the commit `reword`, and delete the attribution lines.
2. Push with `git push --force-with-lease`, so the push fails if someone pushed in the meantime.
3. In every other clone, `git fetch` and move each rewritten branch onto the new remote commits, keeping any local work.

Old commits stay reachable by SHA on the server until it garbage-collects them; on most hosts that needs the administrator.
