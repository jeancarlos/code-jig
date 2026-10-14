---
name: bug-hunt
description: Use when the user asks to hunt for bugs nobody reported, audit a codebase or a path for latent bugs and vulnerabilities, fuzz code, write property-based tests, run mutation testing, or check whether the tests would catch a regression.
---

# Bug hunt

Find real bugs nobody reported, and prove each one with a failing test. Deterministic tools pick the candidates; you judge them in context; generated inputs and mutations find what reading misses.

## Scope

Take scope from the request: a path, a category (security, logic, data integrity, error handling, performance), a minimum severity. Default: the whole repo, or `--base main` on a feature branch.

## 1. Recon, all deterministic

With the harness core on `PYTHONPATH`, or the `harness` launcher on `PATH`:

```
python -m harness analyze --json [--base main] [path]
git ls-files | grep -E "(^|/)\.env($|\.)|\.(pem|key|pfx|p12)$|credentials\.json$|secrets?\.(json|ya?ml)$"
git log --oneline -i -E --grep="security|cve|vuln|bypass|injection|xss|csrf|auth" -n 30
git log --since=90.days --name-only --format= | sort | uniq -c | sort -rn | head -20
git grep -n -i -E "(TODO|FIXME|HACK|XXX).*(security|auth|unsafe|bypass|vuln|temp)|disable.*(auth|ssl|tls|verif)|skip.*validat"
```

PowerShell: replace `grep -E` with `Select-String -Pattern`, and the churn line with `git log --since=90.days --name-only --format= | Group-Object | Sort-Object Count -Descending | Select-Object -First 20 Count, Name`.

- A tracked `.env`, key or credentials file is CRITICAL before anything else: report it now. Removing it does not un-leak it; the secret must be rotated.
- Past fix commits show what this codebase gets wrong; read them and look for the same mistake elsewhere.
- Hotspots, files that are both in the churn list and in `analyze`'s complexity findings, get read first.
- Security TODOs are bugs the authors already found.

## 2. Confirm: the reality gate

For every candidate, read at least 20 lines around it and answer: is this a real problem in this code's actual context? A pattern match on safe code is a false positive; drop it silently. Skip test and mock code unless the test itself hides a bug.

| Severity | Meaning |
|---|---|
| CRITICAL | Exploitable now: auth bypass, injection, remote code execution, data loss |
| HIGH | Likely to break in normal use, or a real security weakness |
| MEDIUM | Needs specific conditions, or a missing guard on a reachable path |
| LOW | Fragile code with no current impact |

Calibrate down: needs authentication plus unusual conditions is MEDIUM, not CRITICAL. A purely theoretical concern is not reported.

When a bug is confirmed, check its siblings; bugs cluster.

| Found | Also check |
|---|---|
| Missing authorization on an endpoint or controller action | The other actions in the same controller or router |
| String-built SQL or command | Every other query or process call in the module |
| Unbounded query or loop over request data | The other list endpoints of the same API |
| Missing input validation | The other POST, PUT and PATCH handlers of the route |
| Swallowed exception | The other catch blocks in the same layer |
| Hardcoded credential | The other config files in the same folder |
| Disposable or subscription not released | The other resources in the same class or component |

With many candidates and a subagent tool available, split them by category, one subagent each, and give every subagent this reality gate and severity table.

## 3. Prove

- A confirmed bug gets a failing test that reproduces it (the `regression-tests` skill). Fix it only if the user asked for fixes.
- Logic that looks wrong but resists a single example gets a property test or a fuzz run.
- For hotspot files, run mutation testing to see what the existing tests would miss.

### Property-based tests

State a rule that holds for all inputs; keep the shrunk counterexample as a fixed test.

| Stack | Library | Shape |
|---|---|---|
| Python | Hypothesis | `@given(st.text())` on a pytest test |
| TS/JS | fast-check | `fc.assert(fc.property(fc.string(), (s) => ...))` |
| .NET | FsCheck (`[Property]` with FsCheck.Xunit) or CsCheck (`Gen.Int.Sample(i => ...)`) | |

Good properties: decode(encode(x)) == x; sorting is idempotent; a result stays inside its bounds; the fast path equals a slow reference.

### Coverage-guided fuzzing

| Stack | Tool | Run |
|---|---|---|
| Python | atheris (Linux x86_64 wheels only) | a script calling `atheris.Setup(sys.argv, test_one_input)` and `atheris.Fuzz()`, run with `-max_total_time=60` |
| TS/JS | jazzer.js | `npx jazzer <fuzz-target-module> -- -max_total_time=60`, the module exporting `fuzz(data)` |
| HTTP APIs | schemathesis | `schemathesis run http://localhost:<port>/openapi.json`, only against a local instance |

Bound every run by time. Each crashing input becomes a test.

### Mutation testing

The tool flips conditions and removes calls, then reruns the tests; a surviving mutant is a regression the tests would miss. Keep it to the hotspot or changed files.

| Stack | Tool | Run |
|---|---|---|
| Python | mutmut (POSIX; on Windows use WSL) | `[tool.mutmut]` with `source_paths = ["src/pkg/module.py"]` in `pyproject.toml`, then `mutmut run`, `mutmut results`, `mutmut show <mutant>` |
| TS/JS | Stryker | `npx stryker run --mutate "src/module.ts"` (`npx stryker init` once) |
| .NET | Stryker.NET | `dotnet new tool-manifest` once, `dotnet tool install dotnet-stryker`, then `DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet stryker --mutate "**/Module.cs"` or `--since:main` |

Each surviving mutant gets a test that kills it, or a sentence on why it is equivalent to the original.

## 4. Report

Most severe first, one block per finding:

```
CRITICAL  Tenant check missing on invoice download
  src/Api/InvoicesController.cs:88
  Any signed-in user can fetch another tenant's invoice by ID. Proven by InvoicesTests.Download_OtherTenant_Forbidden (fails today).
```

End with counts per severity, what was scanned, which tools `analyze` skipped, and the fuzzing and mutation runs with their durations. No finding without a location and either a failing test or the evidence that confirmed it.
