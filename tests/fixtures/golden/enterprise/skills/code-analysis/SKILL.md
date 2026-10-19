---
name: code-analysis
description: Use when the user asks to analyse code quality, find bugs, code smells, complexity, duplication, security issues, leaked secrets or vulnerable dependencies, or asks what Sonar or SonarQube would complain about.
---

# Code analysis

`harness analyze` runs the local analyzers for every stack it finds (.NET, Node, Python, Rust, Java, Go) and prints one summary grouped the way Sonar groups issues. It never downloads a tool and never sends code anywhere.

## Run it

From the repository root run `harness analyze` (the launcher installed with the pack). Without the launcher, point `PYTHONPATH` at the codex-harness checkout, the folder that contains `harness/` (POSIX: `PYTHONPATH=<checkout> python -m harness analyze`; Windows PowerShell: `$env:PYTHONPATH = "<checkout>"; py -3 -m harness analyze`):

```
harness analyze                 # whole repo
harness analyze --base main     # only files changed since main, plus untracked ones
harness analyze --top 30        # more findings per category
harness analyze --json          # machine-readable
```

Exit 0 means clean, 1 means findings or a tool error, 2 means no project, a bad `--base`, or no analyzer installed.

## What runs

| Tool | Stack | Finds |
|---|---|---|
| lizard | all | Cognitive complexity (Sonar's metric, limit 15), cyclomatic complexity (15), functions over 100 lines or 7 parameters, duplicated blocks |
| ruff | Python | Bugs, smells, security (`S` rules, the bandit set) |
| vulture | Python | Dead code at 80% confidence and up: unused imports, variables and arguments, unreachable code, conditions that can never be true. Unused functions and classes score 60%: for a full sweep, set `[tool.vulture]` with `paths` and `min_confidence = 60` in `pyproject.toml`, which `analyze` then uses as-is |
| mypy | Python, with a mypy config | Type errors |
| eslint | Node, with an eslint config | Whatever the config enables; `sonarjs/*` and `security/*` rules are grouped as complexity or security |
| knip | Node | Unused files, exports, types and dependencies; dependencies used but not listed, and imports that do not resolve |
| tsc | Node, with `tsconfig.json` | Type errors |
| dotnet build | .NET | Compiler and analyzer warnings, SonarAnalyzer and Roslynator included when the project references them, and NuGet audit warnings (NU1901-NU1904) for vulnerable packages; restore asks nuget.org for advisories, sending package names |
| clippy | Rust, with `cargo` | `cargo clippy` lints: complexity lints as complexity, `unused*` and `dead_code` as unused, compiler errors as type, the rest bug |
| pmd | Java | PMD 7 quickstart ruleset: Security rules as security, complexity and unused-code rules grouped as such, the rest bug |
| go-vet | Go | `go vet` diagnostics, all as bug |
| semgrep | all, with `.semgrep.yml` or `.semgrep/` | Your own local rules only, run with `--metrics=off` |
| gitleaks | all | Secrets in the working tree, uncommitted files included, and in the git history; the secret itself is never printed |
| osv-scanner | all | Known vulnerabilities in lockfiles, with `--offline`: the first run downloads the vulnerability database, no project data leaves |

`harness analyze` itself sets `DOTNET_CLI_TELEMETRY_OPTOUT=1`, `SEMGREP_SEND_METRICS=off` and `KIOTA_CLI_TELEMETRY_OPTOUT=1` for every tool, in any shell; there is nothing to export. Missing tools are listed as skipped with an install hint.

Analysis executes the repo's own code: `eslint.config.js`, MSBuild targets, mypy plugins and the tools in `node_modules/.bin`. Run it only where you would run the repo's tests.

## Fix in this order

1. `secret`: report it to the user first: the secret must be rotated (only its owner can, and only with their approval), then removed from the code. Removing it from the code does not un-leak it.
2. `security`, then `dependency` (upgrade to the fixed version osv-scanner names).
3. `bug` and `type`.
4. `complexity`: extract functions, return early, replace flag arguments, split by responsibility. Behaviour must not change; run the tests before and after.
5. `unused`: remove the dead code (git keeps it), after checking reflection, dependency injection, public API and framework entry points that tools cannot see.
6. `duplication`: extract the shared code only when both copies change for the same reason.

Rerun with `--base` and the branch this one will merge into (`main` when it exists; check with `git rev-parse --verify main`) to confirm the branch is clean. With no such branch, rerun on the whole repository.

## Add Sonar's rules to a repo

Only with the user's agreement, as dev dependencies:

- .NET: in `Directory.Build.props`, `<PackageReference Include="SonarAnalyzer.CSharp" PrivateAssets="all" />` and `<PackageReference Include="Roslynator.Analyzers" PrivateAssets="all" />`. Raise rules in `.editorconfig`, for example `dotnet_diagnostic.S3776.severity = warning`. SonarAnalyzer is under SonarSource's source-available licence, free to use but not open source; Roslynator and the built-in CA rules are the open-source alternative. Run dotnet commands with `DOTNET_CLI_TELEMETRY_OPTOUT=1`.
- Node: `npm install -D eslint eslint-plugin-sonarjs eslint-plugin-security typescript-eslint`, then in `eslint.config.mjs`:

  ```js
  import sonarjs from "eslint-plugin-sonarjs";
  import security from "eslint-plugin-security";
  export default [sonarjs.configs.recommended, security.configs.recommended];
  ```

- Python: `pip install ruff mypy vulture` in the project's dev dependencies, plus a `[tool.mypy]` section. For stricter typing, pyright in strict mode (`"typeCheckingMode": "strict"` in `pyrightconfig.json`) catches more than mypy's defaults; run it as `pyright --outputjson`.
- TypeScript: `typescript-eslint`'s `strictTypeChecked` config adds `no-floating-promises` and `no-misused-promises`, which catch unawaited async calls; it needs `parserOptions.projectService: true`. Add `knip` as a dev dependency.
- C#: `<Nullable>enable</Nullable>` and `<WarningsAsErrors>nullable</WarningsAsErrors>` turn null-reference warnings into build errors.
- All stacks: `pip install lizard`; gitleaks and osv-scanner from their GitHub releases; semgrep only with local rule files.

What a Sonar server adds that this does not: taint analysis across files and the history dashboard.
