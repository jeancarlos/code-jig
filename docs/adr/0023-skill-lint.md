# 0023: harness lint-skill and the skill-validate skill

Status: accepted (2026-10-15)

## Decision

`harness lint-skill PATH...` checks SKILL.md files mechanically. FAIL (exit 1): no `---` frontmatter, no or invalid `name` (1-64 letters, digits, hyphens), no `description`, a description that does not start with "Use when" or speaks in the first person, frontmatter over 1,024 characters, an `@` link that force-loads a skill file. WARN: name differs from the folder, description in the second person or over 500 characters, body over 500 words, dates in the body, no `## Common mistakes`, a code block over 50 lines. The `skill-validate` skill runs it, then a `reviewer` subagent judges the skill against a ten-rule rubric, one quoted row per rule. The `improve` skill runs `skill-validate` on every skill it writes. A test lints every core skill: none may FAIL.

## Context

The `improve` skill writes overlay skills on machines where CI's linter (`agnix`, fetched with `npx`) is not available. dev-harness had a stdlib linter and a two-pass skill; this ports both to Codex, with the judgement pass on the review tier's other model family instead of a named Claude model.

## Data

- Codex itself requires only the frontmatter block, valid YAML, a name of at most 64 characters and a non-empty description (`codex-rs/skills/src/parser.rs`, rust-v0.162.1). The other rules keep a skill short, triggerable and loadable by Claude Code, which reads the same skills when they are linked into `~/.claude/skills`.
- Every description is sent with every request (ADR 0021), which is why its length is a warning.
- The core skills pass with warnings only: long bodies (`bug-hunt`, `code-analysis`, `redacao`, `web-consensus`) and no `## Common mistakes` in older skills.

## Cost

About 100 lines, eleven tests, one skill.

## Rejected

- Failing on warnings: a reference skill may be long.
- Running the judgement pass in the session that wrote the skill: the author knows what it meant to say.
