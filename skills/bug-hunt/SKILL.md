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
harness analyze --json [--base main] [path]
git ls-files | grep -E "(^|/)\.env($|\.)|\.(pem|key|pfx|p12)$|credentials\.json$|secrets?\.(json|ya?ml)$"
git log --oneline -i -E --grep="security|cve|vuln|bypass|injection|xss|csrf|auth" -n 30
git log --since=90.days --name-only --format= | sort | uniq -c | sort -rn | head -20
git grep -n -i -E "(TODO|FIXME|HACK|XXX).*(security|auth|unsafe|bypass|vuln|temp)|disable.*(auth|ssl|tls|verif)|skip.*validat"
```

PowerShell: write a `NAME=value command` line as `$env:NAME = 'value'; command`, replace `grep -E` with `Select-String -Pattern`, and the churn line with `git log --since=90.days --name-only --format= | Group-Object | Sort-Object Count -Descending | Select-Object -First 20 Count, Name`.

- A tracked `.env`, key or credentials file is CRITICAL before anything else: open it, confirm it holds a real-looking secret and not a placeholder or example value, and report it first. Removing it does not un-leak it; the secret must be rotated.
- Past fix commits show what this codebase gets wrong; read them and look for the same mistake elsewhere.
- Hotspots, files that are both in the churn list and in `analyze`'s complexity findings, get read first.
- Security TODOs are bugs the authors already found.
- `analyze` already reports vulnerable dependencies (osv-scanner, and NuGet audit warnings from `dotnet build`) and dead code (vulture, knip); a function nobody calls is a bug hiding place and a deletion candidate.

### Dependencies, deeper

- One package against osv.dev, sending only its name and version: `curl -s -d '{"package":{"name":"lodash","ecosystem":"npm"},"version":"4.17.20"}' https://api.osv.dev/v1/query` (PowerShell: `Invoke-RestMethod -Method Post -Uri https://api.osv.dev/v1/query -ContentType application/json -Body '{"package":{"name":"lodash","ecosystem":"npm"},"version":"4.17.20"}'`). The fixed versions are in `vulns[].affected[].ranges[].events[].fixed`.
- Upgrade suggestions for npm and Maven, only when the user asked for fixes: `osv-scanner fix --strategy=in-place -L package-lock.json`. It rewrites the lockfile, so review the diff and run the tests. Its default `--data-source deps.dev` sends package names to deps.dev, and `--data-source native` sends them to the package registry; add `--offline-vulnerabilities --download-offline-databases` so the vulnerability matching itself stays local.
- .NET: `DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet list package --vulnerable --include-transitive --format json`. Restore already asks nuget.org for advisories.

### Infrastructure code

- Docker, Kubernetes, Terraform, ARM: `trivy config --disable-telemetry --skip-version-check --skip-check-update --format json .` (the bundled checks; no telemetry, no version or check download).
- Bicep and ARM against Azure's Well-Architected rules: `Install-Module -Name PSRule.Rules.Azure -Scope CurrentUser`, then `Invoke-PSRule -InputPath ./infra -Module PSRule.Rules.Azure -Outcome Fail`. Bicep files need `AZURE_BICEP_FILE_EXPANSION` and ARM templates `AZURE_PARAMETER_FILE_EXPANSION` set to `true` in `ps-rule.yaml`; see its setup pages.

## 2. Confirm: the reality gate

For every candidate, read at least 20 lines around it and answer: is this a real problem in this code's actual context? A pattern match on safe code is a false positive; drop it silently. Skip test and mock code, with one exception: a test that asserts the buggy behaviour is reported together with the bug it locks in.

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

With many candidates and a subagent tool available, split them by category, one subagent each on the default role (judging a bug is not a lookup, so not `explorer`), and give every subagent this reality gate and severity table.

## 3. Prove

- A confirmed bug gets a failing test that reproduces it (the `regression-tests` skill) when the code has a test framework; otherwise record the command and output that reproduce it. Fix it only if the user asked for fixes.
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
| Python | atheris (Linux x86_64 wheels only; on Windows run it in WSL) | a script calling `atheris.Setup(sys.argv, test_one_input)` and `atheris.Fuzz()`, run with `-max_total_time=60` |
| TS/JS | jazzer.js | `npx jazzer <fuzz-target-module> -- -max_total_time=60`, the module exporting `fuzz(data)` |
| .NET | SharpFuzz | a console project with the `SharpFuzz` package and the target assembly instrumented by the `sharpfuzz` tool (`dotnet tool install SharpFuzz.CommandLine` in a tool manifest). With afl-fuzz (Linux) the harness calls `Fuzzer.OutOfProcess.Run(stream => ...)`; with libfuzzer-dotnet (Windows and Linux) it calls `Fuzzer.LibFuzzer.Run(span => ...)`. Follow its README (https://github.com/Metalnem/sharpfuzz) and `docs/libFuzzer.md` |
| HTTP APIs | schemathesis | `schemathesis run http://localhost:<port>/openapi.json`, only against a local instance |

Bound every run by time. Each crashing input becomes a test.

### Mutation testing

The tool flips conditions and removes calls, then reruns the tests; a surviving mutant is a regression the tests would miss. Keep it to the hotspot or changed files.

| Stack | Tool | Run |
|---|---|---|
| Python | mutmut (POSIX; on Windows use WSL) | `[tool.mutmut]` with `source_paths = ["pkg/module.py"]` in `pyproject.toml`, then `mutmut run`, `mutmut results`, `mutmut show <mutant>`. mutmut 3 refuses code imported as `src.…`: run it on a scratch copy with the package renamed. List every non-Python file the tests read in `also_copy`. |
| TS/JS | Stryker | `npx stryker run --mutate "src/module.ts"` (`npx stryker init` once) |
| .NET | Stryker.NET | `dotnet new tool-manifest` once, `dotnet tool install dotnet-stryker`, then `DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet stryker --mutate "**/Module.cs"` or `--since:main` |

Each surviving mutant gets a test that kills it, or a sentence on why it is equivalent to the original.

### Techniques without a new tool

- **Bisect a regression**: `git bisect start <bad> <good>`, then `git bisect run <command that runs the failing test>`; the first bad commit names the cause. Bisect writes inside `.git`, which the Codex sandbox keeps read-only, so request escalation for these commands, and finish with `git bisect reset`.
- **Flaky tests**: shuffle and repeat. pytest with the `pytest-randomly` plugin installed (it shuffles every run) and a loop; `npx jest --randomize`; for .NET, run `DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet test --filter <name>` in a loop of 20. A test that fails only sometimes hides a race, shared state or an order dependency.
- **Differential testing**: run the old and the new implementation (or two libraries) on the same generated inputs and compare.
- **Metamorphic relations**: when the right answer is unknown, test relations instead: sorting a shuffled list gives the same result, filtering twice equals filtering once, a search for a superset term returns a superset.
- **Invariants**: assert what must always hold at module boundaries in tests (totals add up, IDs stay unique) and let property tests drive them.

## 4. Report

Most severe first, one block per finding:

```
CRITICAL  Tenant check missing on invoice download
  src/Api/InvoicesController.cs:88
  Any signed-in user can fetch another tenant's invoice by ID. Proven by InvoicesTests.Download_OtherTenant_Forbidden (fails today).
```

End with counts per severity, what was scanned, which tools `analyze` skipped, and the fuzzing and mutation runs with their durations. No finding without a location and its proof from step 3: a failing test, or where there is no test framework, the command and output that reproduce it.
