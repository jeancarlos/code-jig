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

## Remove it from commits not yet pushed

Amend the last commit's message, or for several commits rebase with `git rebase -i main` and `reword` each one. Do not rewrite history that others already pulled.
