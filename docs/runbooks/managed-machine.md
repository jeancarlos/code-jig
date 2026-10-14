# Runbook: setting up a managed machine

A managed machine (a work laptop, a shared build box, anything someone else administers) runs the core read-only and keeps everything local in its own overlay. Nothing from that overlay flows back to the core.

## Before you start

- Check that the machine's rules allow installing a small stdlib-only Python tool from a public repo.
- Find out whether an administrator applies managed Codex config: `/etc/codex/requirements.toml`, or `%ProgramData%\OpenAI\Codex\requirements.toml` on Windows. `doctor` reports how it differs from `bench/requirements.toml`.
- Install Codex and log in the way that machine expects.
- Python 3.11 or newer.

## 1. Get the core, read-only

Use a tagged release, never a branch:
- Download the tag's source archive from the release page. This leaves no credentials on the machine.
- Or clone the tag over HTTPS: `git clone --branch v0.5.0 https://github.com/jeancarlos/codex-harness`

Do not sign in to a personal account with write access on a machine someone else administers.

## 2. Create the overlay from the example

```sh
cp -r codex-harness/overlay-examples/enterprise ~/codex-overlay
cd ~/codex-overlay && git init && git add -A && git commit -m "chore: local overlay"
```

Keep it local, or push it to a git host that belongs to the same organisation as the machine. Never push it to a personal account.

## 3. Fill the slots

| File | What goes in it |
|---|---|
| `overlay.toml` | `core_version` matching the tag you downloaded. Keep `core_writable = false`. |
| `profiles.toml` | One model ID per tier (`default`, `deep`, `bulk`, `review`), from the models this account may use. `doctor` checks each against Codex's model catalog. |
| `guardian-policy.md` | What Guardian should treat as riskier or safer here: internal hosts, deploy commands, approved package sources. It is added to the upstream policy, never replaces it. |
| `AGENTS.overlay.md` | Rules every session follows. |
| `rules/*.rules` | Optional. Prefer `forbidden`. An `allow` rule runs the command outside the sandbox with no review; read ADR 0009 first. |
| `knowledge/` | Optional. `INDEX.md` plus one fact per file, 150 index lines at most. |
| `skills/` | Optional. One folder per skill with a `SKILL.md`. |

## 4. Install and check

```sh
cd codex-harness
export CODEX_HARNESS_OVERLAY=~/codex-overlay
./install.sh
PYTHONPATH=. python3 -m harness doctor
PYTHONPATH=. python3 -m harness doctor --live
```

On Windows, without running scripts: `set CODEX_HARNESS_OVERLAY=%USERPROFILE%\codex-overlay`, then from the core directory `py -3 -m harness install` and `py -3 -m harness doctor`. Do not use `-ExecutionPolicy Bypass`; endpoint security flags it.

Fix every FAIL; [doctor](doctor.md) explains each line. `--live` runs one short request per tier, so it spends a few tokens; skip it if usage is strictly metered.

## 5. First run

- If plugins are allowed, install superpowers: `codex plugin add superpowers@openai-curated-remote`.
- The first interactive session asks once to trust the `Stop` hook. Accept, or the tracker never collects.
- Behind a TLS-inspecting network, read [network-and-certificates](network-and-certificates.md) first.

## Day to day

- `python -m harness tokens` shows where tokens go; see [tokens](tokens.md). Numbers for the deck go in `docs/deck/data.local.js` on that machine only; it is gitignored.
- Improvements go into overlay slots through the `improve` skill, then `install` and `doctor`.
- Upgrades: [upgrade-and-rollback](upgrade-and-rollback.md).

## What never leaves the machine

The overlay, numbers measured there, internal names, hosts, people and code. The `improve` skill ends with upstream candidates written in generic terms; restate them by hand on the bench if they help anyone.
