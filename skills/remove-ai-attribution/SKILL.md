---
name: remove-ai-attribution
description: "Use when AI attribution leaked into git history - \"Co-authored-by: Codex\", \"Co-Authored-By: Claude\", \"Generated with\" lines in commit messages - and must be removed without changing anything else, when the user asks to scrub or purge AI or co-author marks from commits, or when a push is refused because \"commit messages carry AI attribution\"."
---

# Remove AI attribution

`code-jig scrub` decides everything; do not re-derive its work from git logs. It rewrites commit messages only, only on commits by the user (`git config user.email`, every `codejig.email`, and each `--author`), checks that trees, authors, committers and dates are unchanged, restores every ref if that check fails, and is deterministic: the same history gives the same new SHAs on every clone.

## Procedure

1. `code-jig scrub --dry-run` in the repo lists the commits that carry attribution. Nothing listed: stop.
2. Show the list and get a yes for this repo.
3. `code-jig scrub`. It writes a backup bundle into the git directory, rewrites local branches and tags, and prints one `git push --force-with-lease=...` command per branch. It never pushes.
4. Pushing rewrites shared history. Get a yes for each push command, then run it exactly as printed: the lease refuses the push if someone pushed in the meantime.
5. Every other clone of the repo, with a yes for each clone: `git fetch`, then for each branch the push rewrote run `git cherry origin/<branch> <branch>`. Rewritten commits show `-` (only their message changed); a `+` is a commit that exists only in that clone: stop and ask the user how to carry it over. No `origin/<branch>`: leave the branch alone. Otherwise `git switch <branch>` and `git reset --keep origin/<branch>`. `--keep` refuses to discard uncommitted work.
6. Old commits stay reachable by SHA on the server (and in pull request refs) until the host garbage-collects them. Say so; removing them needs the hosting admin or recreating the repository, which only the user decides.

## Prevention

The code-jig git gate (`git_gate = true` in `overlay.toml`) strips these lines in `commit-msg` and refuses pushes that still carry them. See `docs/runbooks/commit-attribution.md` in the code-jig repository.

## Common mistakes

| Mistake | Instead |
|---|---|
| Rewriting other people's commits | Only the user's identities; pass `--author` for an old address of the user, never for someone else. |
| `git push --force` | Only the printed `--force-with-lease` commands. |
| `--no-verify` to get past the gate | Scrub, then push normally. |
| `git reset --hard` on other clones | `--keep`, so uncommitted work is never lost. |
