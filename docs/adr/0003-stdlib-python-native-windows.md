# 0003: Stdlib Python 3.11 on native Windows and Linux

Status: accepted (2026-10-14)

## Decision
`harness` is written in Python 3.11 or newer using only the standard library. It runs natively on Windows and Linux. `install.sh` and `install.ps1` only find Python and call `harness install`.

## Reason to exist
The tool must run where Codex runs, with nothing to install first.

## Data
- Codex already runs natively on the target Windows machine, so a Linux runtime such as WSL adds nothing.
- One language can be tested on the bench.
- Python 3.11 has `tomllib`, so no TOML dependency is needed.
- CI runs a matrix on `ubuntu-latest` and `windows-latest`. It smoke-tests `install.sh` and `install.ps1`, and pins `@openai/codex@0.162.1` and `agnix@0.57.0`.

## Cost
No third-party packages, no daemon, no network calls from `harness`. Paths must handle spaces and non-ASCII names on both systems.

## Kind
Script.

## Rejected alternatives
- WSL as the runtime. Codex already runs natively, so the migration has no measured gain.
- Node or a compiled binary. A new toolchain, or a binary to commit and trust.
- Third-party Python packages. An install step and a supply-chain surface on a locked-down machine.
