# 0022: harness scrub removes AI attribution from history

Status: accepted (2026-10-15)

## Decision

`harness scrub [PATH] [--author EMAIL] [--dry-run]` removes AI attribution lines from the messages of the user's own commits on local branches and tags, and changes nothing else. "The user" is `user.email`, every `codexharness.email` and each `--author`. It exports with `git fast-export --branches --tags --no-data --show-original-ids --reencode=no --signed-tags=strip --tag-of-filtered-object=rewrite`, rewrites only commit-message `data` blocks of those commits, and imports with `git fast-import --force`. It then compares every old and new commit: headers other than `parent` and signatures must be identical, and the message must equal the old one with the attribution removed. On any difference, or if attribution remains, it restores every branch and tag from the backup bundle it wrote first. It never pushes; it prints one `--force-with-lease` push per branch. The `remove-ai-attribution` skill drives it with the user's approval at each step.

## Context

Codex adds `Co-authored-by: Codex` when the account's attribution setting is on, and on a workspace plan an administrator may control that setting (commit-attribution runbook). The personal setup already had a scrubber (`scrub.py` in dev-harness), but it hard-coded personal addresses, rewrote GitHub repos through `gh`, and needed `git filter-repo`, which a managed machine may not have. This is a clean-room port of its guarantees.

## Data

- `fast-export --no-data` names blobs by SHA, and `fast-import` into the same repository finds them, so the stream holds only commits and tags.
- `fast-import` accepts `original-oid` lines (Git 2.21+); with `--export-marks`, the stream's `mark`/`original-oid` pairs map every old commit to its new one.
- Trees are unchanged, so the checked-out branch's index and working tree stay valid after the refs move; a test keeps an uncommitted edit through a rewrite.
- The same input stream gives the same SHAs: a test scrubs a repo and its clone and compares.
- Signatures cannot survive a message change, and every descendant of a rewritten commit changes too; the verification ignores signature headers for that reason.
- The attribution patterns are `ATTRIBUTION_LINES` in `watermark.py`, shared with the write hook and the git gate (0024); this change added `Claude-Session:`.

## Cost

About 200 lines and nine tests against real repositories. No dependency beyond git.

## Rejected

- `git filter-repo`: an extra install. `git filter-branch --msg-filter`: one process per commit and a deprecated command.
- Rewriting the remote directly or pushing automatically: force-pushing shared history is the user's decision, and the printed leases make it safe.
- Purging old SHAs from the server: only the host can, and on most hosts that means recreating the repository.
