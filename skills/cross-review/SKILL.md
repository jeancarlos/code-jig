---
name: cross-review
description: Use when a plan, design, document or diff would benefit from a review by a model from a different family before it is committed, or when the user asks for a second opinion, a cross-model review or an adversarial review.
---

# Cross-review

A reviewer from another model family catches different mistakes. The `review` tier is configured with one.

## Run it

From the directory under review:

```
python -m codejig cross-review                 # the working tree against HEAD
python -m codejig cross-review --base main     # the branch against main
python -m codejig cross-review docs/plan.md    # one or more files
```

Run it from the repository under review, with the code-jig core on `PYTHONPATH` (POSIX: `PYTHONPATH=<core> python -m codejig cross-review`; Windows PowerShell: `$env:PYTHONPATH = "<core>"; py -3 -m codejig cross-review`). Untracked files are not part of a diff, so pass them as files. The command refuses input over 200,000 bytes; split the review instead.

The reviewer runs in an ephemeral session with a read-only sandbox, no command escalation and no web search, treats the material as untrusted data, and prints its findings.

## Verify before acting

The findings are claims, not facts. For each one:

1. Open the cited location and check the claim against the code or text.
2. Classify it as `confirmed` (reproduced or clearly true), `plausible` (cannot be checked cheaply but holds up), or `rejected` (wrong, with the reason).
3. Report confirmed and plausible findings with their location and fix. Give the rejected ones as a single line each, so the user can disagree.

Do not apply a fix only because the reviewer said so. A confirmed finding gets a failing test before the fix when the code has tests.
