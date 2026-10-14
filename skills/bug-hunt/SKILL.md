---
name: bug-hunt
description: Use when the user asks to hunt for bugs, fuzz code, write property-based tests, run mutation testing, or check whether the tests would catch a regression.
---

# Bug hunt

Let generated inputs and generated faults find what hand-written examples miss. Every bug found becomes a normal regression test (the `regression-tests` skill).

## Pick the target

Parsers, serializers, validators, money and date arithmetic, anything that takes outside input. Start with the changed files: `git diff --name-only main...HEAD`.

## Property-based tests

State a rule that holds for all inputs, let the library search for a counterexample, keep the shrunk failing case as a fixed test.

| Stack | Library | Shape |
|---|---|---|
| Python | Hypothesis | `@given(st.text())` on a pytest test |
| TS/JS | fast-check | `fc.assert(fc.property(fc.string(), (s) => ...))` |
| .NET | FsCheck (`[Property]` with FsCheck.Xunit) or CsCheck (`Gen.Int.Sample(i => ...)`) | |

Good properties: decode(encode(x)) == x; sorting is idempotent; a result stays inside its bounds; the fast path equals the slow reference implementation.

## Coverage-guided fuzzing

| Stack | Tool | Run |
|---|---|---|
| Python | atheris (Linux x86_64 wheels only) | a script calling `atheris.Setup(sys.argv, test_one_input)` and `atheris.Fuzz()`, run with `-max_total_time=60` |
| TS/JS | jazzer.js | `npx jazzer <fuzz-target-module> -- -max_total_time=60`, the module exporting `fuzz(data)` |
| HTTP APIs | schemathesis | `schemathesis run http://localhost:<port>/openapi.json`, only against a local instance |

Bound every run by time. Save crashing inputs next to the target and turn each into a test.

## Mutation testing

The tool changes the code (flips a condition, removes a call) and reruns the tests. A mutant that survives is a regression the tests would miss. Keep it to the changed files; whole-repo runs take hours.

| Stack | Tool | Run |
|---|---|---|
| Python | mutmut (POSIX; on Windows use WSL) | `[tool.mutmut]` with `source_paths = ["src/pkg/module.py"]` in `pyproject.toml`, then `mutmut run`, `mutmut results`, `mutmut show <mutant>` |
| TS/JS | Stryker | `npx stryker run --mutate "src/module.ts"` (`npx stryker init` once) |
| .NET | Stryker.NET | `dotnet new tool-manifest` once, `dotnet tool install dotnet-stryker`, then `DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet stryker --mutate "**/Module.cs"` or `--since:main` |

For each surviving mutant: write the test that kills it, or say why the mutant is equivalent to the original code.

## Report

List what ran, for how long, every failure found with its regression test, and surviving mutants with their decision.
