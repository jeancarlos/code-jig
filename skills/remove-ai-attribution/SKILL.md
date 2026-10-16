---
name: remove-ai-attribution
description: "Use when AI attribution leaked into git history - \"Co-authored-by: Codex\", \"Co-Authored-By: Claude\", \"Generated with\" lines in commit messages - and must be removed without changing anything else, when the user asks to scrub or purge AI or co-author marks from commits, or when a push is refused because \"commit messages carry AI attribution\"."
---

# Remove AI attribution

A safety net, not the rule: the rule (no AI attribution anywhere) is in the base instructions, and the git gate strips trailers before they land. Use this only when attribution already reached commits.

`code-jig scrub` decides everything; do not re-derive its work from git logs. It rewrites commit messages only, only on commits by the user (`git config user.email`, every `codejig.email`, and each `--author`), checks that trees, authors, committers and dates are unchanged, restores every ref if that check fails, and is deterministic: the same history gives the same new SHAs on every clone.

## Procedure

1. `code-jig scrub --dry-run` in the repo lists the commits that carry attribution. Nothing listed: stop.
2. Show the list and get a yes for this repo.
3. `code-jig scrub`. It saves a backup bundle in the git directory first and prints its path: that is the safe point. Keep the path in the reply. It rewrites local branches and tags, prints one `git push --force-with-lease=...` command per branch, and never pushes.
4. Pushing rewrites shared history. Get a yes for each push command, then run it exactly as printed: the lease refuses the push if someone pushed in the meantime.
5. Other clones: never repair them by hand. In each one, with a yes, run this procedure from step 1. Scrub gives the same SHAs there, so after `git fetch`, `git status -sb` shows the branch even with its upstream and there is nothing to push. Anything else (ahead, behind or diverged) means that clone has its own commits: stop and ask the user.
6. Old commits stay reachable by SHA on the server (and in pull request refs) until the host garbage-collects them. Say so; removing them needs the hosting admin or recreating the repository, which only the user decides.

## Undo

Before pushing, the backup restores every branch and tag: `git fetch --update-head-ok <bundle> "+refs/heads/*:refs/heads/*" "+refs/tags/*:refs/tags/*"`. After pushing, restoring needs another lease-protected push, which only the user decides.

## Common mistakes

| Mistake | Instead |
|---|---|
| Rewriting other people's commits | Only the user's identities; pass `--author` for an old address of the user, never for someone else. |
| `git push --force` | Only the printed `--force-with-lease` commands. |
| `--no-verify` to get past the gate | Scrub, then push normally. |
| Resetting other clones to the remote | Run this procedure in each clone (step 5); a clone that differs is the user's call. |
| Deleting the backup bundle | Keep it until every clone matches the remote. |
