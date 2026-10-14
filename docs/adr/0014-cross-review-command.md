# 0014: Cross-review is a command plus a skill

Status: accepted (2026-10-14)

## Decision
`harness cross-review [--base REF] [FILE ...]` collects the material deterministically (`git diff <base or HEAD>`, or the named files) and pipes it, wrapped in markers and labelled untrusted data, to `codex exec --profile review --sandbox read-only --ephemeral -c approvals_reviewer="user" -c web_search="disabled" --skip-git-repo-check -o <file> -`. It then prints the findings. It refuses empty input, binary files, a failed `git diff`, and anything over 200,000 bytes, all before any model call. The `cross-review` skill tells the agent when to run it and to verify each finding before acting on it.

## Reason to exist
A reviewer from another model family catches different mistakes. Gathering the material and calling Codex is deterministic, so it is a script. Judging the findings is the model's job.

## Data
- The `review` tier uses a model family different from `default` (0007), and doctor warns when they match.
- The `codex exec` flags come from `codex exec --help` on the bench: `--profile`, `--sandbox`, `--ephemeral`, `-o`, and `-` for stdin.

- `codex exec` forces `approval_policy = never` unless the resolved reviewer is `auto_review` (`codex-rs/exec/src/lib.rs`, rust-v0.162.1). Every tier profile sets `auto_review`, so without the `approvals_reviewer="user"` override the reviewer could escalate a command, and Guardian allows egress that the user turn authorizes. The reviewed material is in the user turn.

## Cost
About 60 lines. One review costs the review tier's tokens for the material, which is why the size cap exists.

## Kind
Script orchestration plus model judgement.

## Rejected alternatives
- A gateway to another vendor's model: a managed machine may allow Codex only.
- Applying the reviewer's fixes automatically: findings are claims until verified.
