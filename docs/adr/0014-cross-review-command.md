# 0014: Cross-review is a command plus a skill

Status: accepted (2026-10-14)

## Decision
`harness cross-review [--base REF] [FILE ...]` collects the material deterministically (`git diff <base or HEAD>`, or the named files) and pipes it, with a fixed review prompt, to `codex exec --profile review --sandbox read-only --ephemeral --skip-git-repo-check -o <file> -`. It then prints the findings. It refuses empty input, binary files, a failed `git diff`, and anything over 200,000 bytes, all before any model call. The `cross-review` skill tells the agent when to run it and to verify each finding before acting on it.

## Reason to exist
A reviewer from another model family catches different mistakes. Gathering the material and calling Codex is deterministic, so it is a script. Judging the findings is the model's job.

## Data
- The `review` tier uses a model family different from `default` (0007), and doctor warns when they match.
- The `codex exec` flags come from `codex exec --help` on the bench: `--profile`, `--sandbox`, `--ephemeral`, `-o`, and `-` for stdin.

## Cost
About 60 lines. One review costs the review tier's tokens for the material, which is why the size cap exists.

## Kind
Script orchestration plus model judgement.

## Rejected alternatives
- A gateway to another vendor's model: the corporate laptop allows Codex only.
- Applying the reviewer's fixes automatically: findings are claims until verified.
