---
name: regression-tests
description: Use when fixing a bug, changing behaviour or adding a feature in code that has tests, or when the user asks whether a change is covered by tests, wants regression tests, or wants coverage of the changed lines.
---

# Regression tests

Every behaviour change ships with a test that fails without the change and passes with it.

## Bug fix

1. Write the smallest test that reproduces the bug through the public interface.
2. Run it and watch it fail for the reason in the bug report, not for a typo or a missing import.
3. Fix the code, not the test.
4. Run the test, then the whole suite.

## New or changed behaviour

Write the test first, watch it fail, implement, watch it pass. When the change comes from a requirement, tag the test with its ID (see the `hld-trace` skill).

## Follow the repo

Put tests where the repo already keeps them, with its framework, naming and fixtures. Do not add a test framework the repo does not use.

## Coverage of the changed lines

[diff-cover](https://github.com/Bachmann1234/diff_cover) reads a Cobertura XML report and lists the changed lines no test executes. Install it with `pip install diff-cover`.

| Stack | Produce `coverage.xml` |
|---|---|
| Python | `coverage run -m pytest`, then `coverage xml` (in PowerShell 5.1, which has no `&&`: `coverage run -m pytest; coverage xml`) |
| .NET | `DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet test --collect:"XPlat Code Coverage"` writes `TestResults/*/coverage.cobertura.xml` |
| Node with c8 | `npx c8 --reporter=cobertura npm test` writes `coverage/cobertura-coverage.xml` |
| Vitest | `npx vitest run --coverage --coverage.reporter=cobertura` |
| Jest | `npx jest --coverage --coverageReporters=cobertura` |

Windows PowerShell has no `NAME=value command` form: write the variable first in the same command, for example `$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'; dotnet test`.

Then:

```
diff-cover <report.xml> --compare-branch=origin/main --include-untracked
```

Pass several reports at once for a multi-stack repo. Every uncovered changed line is either covered by a new test or explained: generated code, logging, a branch that only a real outage reaches.

## Is the test good enough

A test that never fails proves nothing. For important logic, run mutation testing on the changed files (the `bug-hunt` skill): a surviving mutant is a regression the tests would miss.

## Report

Name the test that failed before the change and passes after it, the full suite result, and each changed line diff-cover listed with the test that now covers it or the reason it stays uncovered.
