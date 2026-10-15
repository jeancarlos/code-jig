# 0016: Deterministic code-quality tooling, on demand

Status: accepted (2026-10-14)

## Decision

The core ships two stdlib commands and five skills that Codex uses when asked:

- `harness analyze` detects .NET, Node and Python, runs the locally installed analyzers (lizard, ruff, mypy, eslint, tsc, `dotnet build`, semgrep with local rules, gitleaks, osv-scanner) and prints one summary grouped like Sonar: security, secret, dependency, bug, type, complexity, duplication.
- `harness trace` maps requirement IDs from any source to the test files that cite them.
- Skills: `code-analysis`, `regression-tests`, `hld-trace`, `bug-hunt`, `codegen`.

gitleaks runs twice: on the working tree, so uncommitted secrets are found before they are committed, and on the history when the folder is a git repository. A timed-out tool is killed with every process it started. Exit 2 means nothing could run, so an empty toolbox is never mistaken for a clean repo.

Nothing is enforced: no blocking `Stop` hook, no gate. A tool is never downloaded at run time, every known telemetry opt-out is set, and a tool that crashes, times out or prints something unreadable becomes an error line, never a crash.

## Context

The goal is to let Codex answer countable questions (how complex, how duplicated, which lines are untested, which requirements have no test) by running code instead of reasoning, which is faster and spends fewer tokens. The work stacks are C#/.NET, TypeScript/JavaScript and Python. Requirements live outside the repo, so the trace takes IDs from any command's output.

Sonar's own rules run locally without a server: SonarAnalyzer.CSharp inside `dotnet build`, eslint-plugin-sonarjs inside eslint, and lizard's `-Ecognitive` computes Sonar's cognitive complexity for every language. What a Sonar server adds and this does not: cross-file taint analysis and the history dashboard.

Every candidate was checked on 2026-10-14 against its GitHub repo, PyPI, npm or NuGet for licence, last release and telemetry.

## Rejected

- A blocking `Stop` hook that refuses to finish until gates pass (Codex supports it: `{"decision":"block"}`). The user wants the tools available when asked, not imposed.
- The pre-commit framework: it downloads hooks from GitHub at run time and only gates commits.
- complexipy: lizard's cognitive extension covers Python as well as C# and TypeScript with one tool.
- jscpd: lizard's duplicate extension covers the same need without a Node dependency.
- opengrep: its telemetry could not be confirmed. Semgrep CE with local rules and `--metrics=off` is documented to send nothing.
- Security Code Scan: no release since 2022.
- Hosted documentation or analysis services: they would receive the code.

## Amendment (v0.6.0, 2026-10-14)

- `analyze` adds vulture (Python) and knip (Node) for dead code, under a new `unused` category, and reads project-level MSBuild warnings, so NuGet audit warnings `NU1901`-`NU1904` become `dependency` findings. They carry no line number, which is why the first parser missed them.
- SharpFuzz is in the `bug-hunt` skill after all. Its GitHub releases stop in January 2025, but NuGet has 2.3.0 from June 2026; the first check read the wrong source.
- `bug-hunt` gained recipes for osv.dev single-package queries, `osv-scanner fix` (its default deps.dev source receives package names), trivy config (`--disable-telemetry --skip-check-update`, because trivy reports flag usage otherwise), PSRule for Azure, and techniques that need no tool: bisect, flaky-test hunting, differential and metamorphic testing.
- Checked and skipped: Bearer CLI (ELv2, source-available, single-file taint only), RESTler (no published releases), CodeQL (licence excludes private code without GitHub Advanced Security). osv-scanner call analysis covers only Go and Rust.
- The standalone `jeancarlos/claude-bug-hunt` repository is archived; the skill lives here.

## Consequences

- The five skill descriptions add roughly 300 tokens to every request, mostly served from the prompt cache.
- `harness analyze` executes the repo's own configs and build, so it carries the same trust as running the repo's tests.
- Output formats of nine external tools are parsed. CI installs pinned versions of lizard, ruff, gitleaks and osv-scanner on Linux and Windows and runs the real-tool tests and `analyze` on this repo, so a format change shows up as a failing job.
- SonarAnalyzer.CSharp is source-available (SonarSource Source-Available License v1), not open source; the skill names Roslynator and the CA rules as the open alternative.
