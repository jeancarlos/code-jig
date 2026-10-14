# Runbook: code quality without a server

Two deterministic commands and five skills give Codex Sonar-style analysis, requirement tracing, regression tests, bug hunting and code generation, all local and all on demand. Nothing runs unless you ask.

## Commands

All examples assume the core on `PYTHONPATH` (see [daily-use](daily-use.md) for an alias) and the repository under test as the current directory.

### `harness analyze`

```sh
harness analyze                    # the whole repo
harness analyze --base main        # only files changed since main, plus untracked files
harness analyze services/api       # one folder; stacks are detected there
harness analyze --top 30 --json    # more findings, machine-readable
harness analyze --timeout 1200     # per tool, in seconds (default 600)
```

It finds the stacks from marker files (`*.sln`, `*.slnx` or `*.csproj` for .NET; `package.json` for Node; `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt` or `.py` files for Python), runs every applicable tool that is installed, and prints:

```
analyze: python
security 2  secret 0  dependency 1  bug 7  type 0  complexity 3  duplication 1
== security (2)
  app/db.py:41  S608  Possible SQL injection vector through string-based query construction
  ...
skipped: mypy (no mypy config)
error: semgrep: exit 2: ...
```

Exit 0: clean. Exit 1: findings or a tool error. Exit 2: no project found, or a bad `--base`.

| Tool | Runs when | Category mapping |
|---|---|---|
| lizard | always, on tracked source files | `complexity` above Sonar's defaults: cognitive 15, cyclomatic 15, 100 lines, 7 parameters; `duplication` for repeated blocks |
| ruff | Python | `S*` security, `C90*`/`PLR09*` complexity, the rest bug; the repo's ruff config applies, plus `S` and `B` |
| mypy | Python with a mypy config | type |
| eslint | Node with an eslint config | `sonarjs/*` complexity and security rules mapped, `security/*` security, the rest bug |
| tsc | Node with `tsconfig.json` | type |
| dotnet build | .NET with a solution or project at the root | `S3776` and other complexity rules, `CA3*`, `CA5*` and known Sonar security rules as security, `CS*` as type, the rest bug |
| semgrep | `.semgrep.yml`, `.semgrep.yaml` or `.semgrep/` exists | security |
| gitleaks | always | secret, never printing the secret |
| osv-scanner | always | dependency |

`dotnet build` runs with `--no-incremental`, because an incremental build skips the compiler and with it every analyzer warning.

### `harness trace`

```sh
harness trace ids.txt                        # one ID per line, first word of each line
harness trace ids.json                       # [1, 2], [{"id": 1}], or {"workItems": [...]}
az boards query --wiql "..." -o json | harness trace -
harness trace ids.txt --pattern "AB#{id}"    # match a different tag
harness trace ids.txt --path services/api --json
```

The default tag is `REQ-<id>`, case-insensitive, with word boundaries: `REQ-12` never matches `REQ-123`. Only tracked test files are read. Exit 0 when every ID has a test and no test cites an unknown ID, 1 otherwise, 2 for unusable input or a bad pattern.

## Skills

| Skill | Ask for | What Codex does |
|---|---|---|
| `code-analysis` | "analyse this", "what would Sonar say" | Runs `harness analyze`, fixes by category (secrets first), sets up Sonar rule packages only with your agreement |
| `regression-tests` | bug fixes, "is this covered" | Failing test first, then diff-cover on the changed lines |
| `hld-trace` | "does this follow the HLD" | Pulls requirement IDs (Azure DevOps, GitHub issues, Markdown), runs `harness trace`, closes gaps |
| `bug-hunt` | "fuzz this", "would the tests catch it" | Property tests, coverage-guided fuzzing, mutation testing on changed files |
| `codegen` | API clients, codemods, scaffolding | NSwag, Kiota, openapi-generator, ast-grep, the stack's templates, all from a script kept in the repo |

## Installing the tools

None are required; each missing one is reported as skipped. Install them as the repo's dev dependencies where the stack has a place for them, otherwise on the machine:

| Tool | Install |
|---|---|
| lizard, ruff, mypy, semgrep, diff-cover | `pip install` (or the project's dev dependency file) |
| eslint, eslint-plugin-sonarjs, eslint-plugin-security, typescript | `npm install -D` |
| SonarAnalyzer.CSharp, Roslynator.Analyzers | `PackageReference` with `PrivateAssets="all"` in `Directory.Build.props` |
| gitleaks, osv-scanner | release binaries from their GitHub pages, or the machine's package manager |

CI pins the versions it tests against: lizard 1.24.1, ruff 0.17.0, gitleaks 8.30.1, osv-scanner 2.7.0.

## Privacy

- No tool is downloaded at run time; `node_modules/.bin` is used before `PATH` so the repo's pinned versions win.
- Every tool runs with `DOTNET_CLI_TELEMETRY_OPTOUT=1`, `DOTNET_NOLOGO=1`, `SEMGREP_SEND_METRICS=off`, `SEMGREP_ENABLE_VERSION_CHECK=0` and `KIOTA_CLI_TELEMETRY_OPTOUT=1`.
- semgrep runs only local rule files, with `--metrics=off` and `--disable-version-check`.
- osv-scanner runs with `--offline --download-offline-databases`: it downloads the public vulnerability database and sends nothing about the project.
- `harness analyze` executes the repo's own code (eslint configs, MSBuild targets, mypy plugins, `node_modules/.bin`). Run it only where you would run the repo's tests.

## False positives

- gitleaks: add the finding's fingerprint to `.gitleaksignore` in the repo.
- ruff, eslint, analyzers: configure or suppress the rule in the repo's own config, with the reason in the commit message.
- lizard: thresholds are fixed at Sonar's defaults. A function above them is worth a look even when it stays.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `harness: no .NET, Node or Python project found` | No marker file at the path given; point it at the project folder |
| `error: <tool>: exit N: ...` | The tool ran and failed without findings; the message is its own first line of output |
| `error: <tool>: unreadable output` | The tool's output format changed; report it with the tool's version |
| `error: <tool>: timed out after 600s` | Raise `--timeout`, or analyze a subfolder |
| `dotnet` skipped with "no solution or project at the root" | Run it from the folder with the `.sln` or `.csproj` |
