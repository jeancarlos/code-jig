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

It finds the stacks from marker files at the given path (`*.sln` or `*.slnx` there, or `*.csproj` there or one folder down, for .NET; `package.json` for Node; `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, or `.py` files there or one folder down, for Python), runs every applicable tool that is installed, and prints:

```
analyze: python
security 2  secret 0  dependency 1  bug 7  type 0  unused 4  complexity 3  duplication 1
== security (2)
  app/db.py:41  S608  Possible SQL injection vector through string-based query construction
  ...
skipped: mypy (no mypy config)
error: semgrep: exit 2: ...
```

Exit 0: clean. Exit 1: findings or a tool error. Exit 2: no project found, a bad `--base`, or no analyzer installed at all (every tool skipped).

| Tool | Runs when | Category mapping |
|---|---|---|
| lizard | always, on source files that git tracks or would track (ignored files are skipped) | `complexity` above cognitive 15 (Sonar's default for S3776), cyclomatic 15, 100 lines of code or 7 parameters (the harness's limits); `duplication` for repeated blocks |
| ruff | Python | `S` followed by digits (the bandit rules) security, `C90*`/`PLR09*` complexity, the rest bug; the repo's ruff config applies, plus `S` and `B` |
| vulture | Python | `unused`: dead functions, classes, imports and unreachable code at 80% confidence or more |
| mypy | Python with a mypy config | type |
| eslint | Node with an eslint config | `sonarjs/*` complexity and security rules mapped, `security/*` security, the rest bug |
| knip | Node | `unused` files, exports, types and dependencies; `bug` for unlisted or unresolved imports and import cycles |
| tsc | Node with `tsconfig.json` | type |
| dotnet build | .NET with a solution or project at the root | `S3776` and other complexity rules, `CA3*`, `CA5*` and known Sonar security rules as security, `CS*` as type, NuGet audit warnings `NU1901`-`NU1904` as dependency (project-level warnings carry no line), the rest bug |
| semgrep | `.semgrep.yml`, `.semgrep.yaml` or `.semgrep/` exists | security |
| gitleaks | always on the working tree, uncommitted and untracked files included (ignored files skipped); again on the git history when `.git` exists | secret, never printing the secret; the message carries gitleaks' fingerprint |
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

The default tag is `REQ-<id>`, case-insensitive, with word boundaries: `REQ-12` never matches `REQ-123`. `--pattern` is literal text with one `{id}` placeholder; characters such as `(`, `[` or `#` match themselves. Test files that git tracks or would track are read; ignored files are skipped.

The ID file may be UTF-8 or UTF-16 (what Windows PowerShell 5.1 writes with `>`). Plain lines may be bare IDs, `REQ-12: title`, Markdown list items or numbered items. Text that starts with `[` or `{` must be valid JSON.

Exit 0 when every ID has a test and no test cites an unknown ID, 1 otherwise, 2 for unreadable or undecodable input, broken JSON, no IDs, or a pattern without `{id}`.

## Skills

| Skill | Ask for | What Codex does |
|---|---|---|
| `code-analysis` | "analyse this", "what would Sonar say" | Runs `harness analyze`, fixes by category (secrets first), sets up Sonar rule packages only with your agreement |
| `regression-tests` | bug fixes, "is this covered" | Failing test first, then diff-cover on the changed lines |
| `hld-trace` | "does this follow the HLD" | Pulls requirement IDs (Azure DevOps, GitHub issues, Markdown), runs `harness trace`, closes gaps |
| `bug-hunt` | "hunt for bugs", "fuzz this", "would the tests catch it" | Deterministic recon, a reality gate on every candidate, proof by failing test; property tests, fuzzing (including SharpFuzz for .NET), mutation testing; osv.dev lookups and `osv-scanner fix`; trivy and PSRule for infrastructure code; bisect, flaky-test and differential techniques |
| `codegen` | API clients, codemods, scaffolding | NSwag, Kiota, openapi-generator, ast-grep, the stack's templates, all from a script kept in the repo |

## Installing the tools

None are required; each missing one is reported as skipped. Install them as the repo's dev dependencies where the stack has a place for them, otherwise on the machine:

| Tool | Install |
|---|---|
| lizard, ruff, vulture, mypy, semgrep, diff-cover | `pip install` (or the project's dev dependency file) |
| eslint, eslint-plugin-sonarjs, eslint-plugin-security, typescript, knip | `npm install -D` |
| SonarAnalyzer.CSharp, Roslynator.Analyzers | `PackageReference` with `PrivateAssets="all"` in `Directory.Build.props` |
| gitleaks, osv-scanner | release binaries from their GitHub pages, or the machine's package manager |

CI pins the versions it tests against: lizard 1.24.1, ruff 0.17.0, vulture 2.16, knip 6.41.0, gitleaks 8.30.1, osv-scanner 2.7.0.

## Privacy

- No tool is downloaded at run time; `node_modules/.bin` is used before `PATH` so the repo's pinned versions win.
- Every tool runs with `DOTNET_CLI_TELEMETRY_OPTOUT=1`, `DOTNET_NOLOGO=1`, `SEMGREP_SEND_METRICS=off`, `SEMGREP_ENABLE_VERSION_CHECK=0` and `KIOTA_CLI_TELEMETRY_OPTOUT=1`.
- semgrep runs only local rule files, with `--metrics=off` and `--disable-version-check`.
- osv-scanner runs with `--offline --download-offline-databases`: it downloads the public vulnerability database and sends nothing about the project.
- `dotnet build` runs NuGet's audit during restore, which asks nuget.org about the project's package names and versions, as every restore already does.
- Python tools run with `PYTHONUTF8=1`, so file lists and output stay UTF-8 on Windows; `analyze` and `trace` write UTF-8 to the console too.
- `harness analyze` executes the repo's own code (eslint configs, MSBuild targets, mypy plugins, `node_modules/.bin`). Run it only where you would run the repo's tests.

## False positives

- gitleaks: add the fingerprint shown in the finding to `.gitleaksignore` in the repo.
- ruff, eslint, analyzers: configure or suppress the rule in the repo's own config, with the reason in the commit message.
- lizard: thresholds are fixed at Sonar's defaults. A function above them is worth a look even when it stays.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `harness: no .NET, Node or Python project found` | No marker file at the path given; point it at the project folder |
| `error: <tool>: exit N: ...` | The tool ran and failed without findings; the message is its own first line of output |
| `error: <tool>: unreadable output` | The tool's output format changed; report it with the tool's version |
| `error: <tool>: timed out after 600s` | Raise `--timeout`, or analyze a subfolder. The tool and every process it started are killed. |
| `harness: no analyzer ran` | Every tool was skipped; install at least one from the skipped list |
| `dotnet` skipped with "no solution or project at the root" | Run it from the folder with the `.sln` or `.csproj` |
