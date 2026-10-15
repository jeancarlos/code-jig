---
name: code-analysis
description: Use when the user asks to analyse code quality, find bugs, code smells, complexity, duplication, security issues, leaked secrets or vulnerable dependencies, or asks what Sonar or SonarQube would complain about.
---

# Code analysis

`harness analyze` runs the local analyzers for every stack it finds (.NET, Node, Python) and prints one summary grouped the way Sonar groups issues. It never downloads a tool and never sends code anywhere.

## Run it

From the repository root, with the harness core on `PYTHONPATH` (POSIX: `PYTHONPATH=<core> python -m harness analyze`; Windows PowerShell: `$env:PYTHONPATH = "<core>"; py -3 -m harness analyze`):

```
python -m harness analyze                 # whole repo
python -m harness analyze --base main     # only files changed since main, plus untracked ones
python -m harness analyze --top 30        # more findings per category
python -m harness analyze --json          # machine-readable
```

Exit 0 means clean, 1 means findings or a tool error, 2 means no project, a bad `--base`, or no analyzer installed.

## What runs

| Tool | Stack | Finds |
|---|---|---|
| lizard | all | Cognitive complexity (Sonar's metric, limit 15), cyclomatic complexity (15), functions over 100 lines or 7 parameters, duplicated blocks |
| ruff | Python | Bugs, smells, security (`S` rules, the bandit set) |
| vulture | Python | Dead code: unused functions, classes, imports, unreachable code (80% confidence and up) |
| mypy | Python, with a mypy config | Type errors |
| eslint | Node, with an eslint config | Whatever the config enables; `sonarjs/*` and `security/*` rules are grouped as complexity or security |
| knip | Node | Unused files, exports, types and dependencies; unlisted or unresolved imports and import cycles |
| tsc | Node, with `tsconfig.json` | Type errors |
| dotnet build | .NET | Compiler and analyzer warnings, SonarAnalyzer and Roslynator included when the project references them, and NuGet audit warnings (NU1901-NU1904) for vulnerable packages; restore asks nuget.org for advisories, sending package names |
| semgrep | all, with `.semgrep.yml` or `.semgrep/` | Your own local rules only, run with `--metrics=off` |
| gitleaks | all | Secrets in the working tree, uncommitted files included, and in the git history; the secret itself is never printed |
| osv-scanner | all | Known vulnerabilities in lockfiles, with `--offline`: the first run downloads the vulnerability database, no project data leaves |

The command sets `DOTNET_CLI_TELEMETRY_OPTOUT=1`, `SEMGREP_SEND_METRICS=off` and `KIOTA_CLI_TELEMETRY_OPTOUT=1` for every tool. Missing tools are listed as skipped with an install hint.

Analysis executes the repo's own code: `eslint.config.js`, MSBuild targets, mypy plugins and the tools in `node_modules/.bin`. Run it only where you would run the repo's tests.

## Fix in this order

1. `secret`: rotate the secret first, then remove it. Removing it from the code does not un-leak it.
2. `security`, then `dependency` (upgrade to the fixed version osv-scanner names).
3. `bug` and `type`.
4. `complexity`: extract functions, return early, replace flag arguments, split by responsibility. Behaviour must not change; run the tests before and after.
5. `unused`: delete it, after checking reflection, dependency injection, public API and framework entry points that tools cannot see.
6. `duplication`: extract the shared code only when both copies change for the same reason.

Rerun with `--base main` to confirm the branch is clean.

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
