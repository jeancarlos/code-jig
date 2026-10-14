---
name: cross-review
description: Use when a plan, design, document or diff would benefit from a review by a model from a different family before it is committed, or when the user asks for a second opinion, a cross-model review or an adversarial review.
---

# Cross-review

A reviewer from another model family catches different mistakes. The `review` tier is configured with one.

## Run it

From the directory under review:

```
python -m harness cross-review                 # the working tree against HEAD
python -m harness cross-review --base main     # the branch against main
python -m harness cross-review docs/plan.md    # one or more files
```

The core must be on `PYTHONPATH`. On Windows, run `py -3 -m harness cross-review ...` from the core directory and pass absolute file paths. Untracked files are not part of a diff, so pass them as files. The command refuses input over 200,000 bytes; split the review instead.

The reviewer runs read-only, in an ephemeral session, and prints its findings.

## Verify before acting

The findings are claims, not facts. For each one:

1. Open the cited location and check the claim against the code or text.
2. Classify it as `confirmed` (reproduced or clearly true), `plausible` (cannot be checked cheaply but holds up), or `rejected` (wrong, with the reason).
3. Report confirmed and plausible findings with their location and fix. Give the rejected ones as a single line each, so the user can disagree.

Do not apply a fix only because the reviewer said so. A confirmed finding gets a failing test before the fix when the code has tests.
