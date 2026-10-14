# Runbook: setting up a work overlay

A work machine runs the core read-only and keeps everything work-specific in its own overlay. Nothing from that overlay flows back to the core.

## Before you start

- Read your contract's IP clause and any open-source policy.
- Find out whether IT applies managed Codex config: `/etc/codex/requirements.toml`, or `%ProgramData%\OpenAI\Codex\requirements.toml` on Windows. `doctor` reports how it differs from `bench/requirements.toml`.
- Install Codex and log in through the company's usual route.
- Python 3.11 or newer.

## 1. Get the core, read-only

Use a tagged release, never a branch:
- Download the tag's source archive from the GitHub release page. This leaves no credentials on the machine.
- Or clone over HTTPS with a read-only, fine-grained token: `git clone --branch v0.4.1 https://github.com/jeancarlos/codex-harness`

Do not sign in to a personal account with write access on a work machine.

## 2. Create the overlay from the example

```sh
cp -r codex-harness/overlay-examples/enterprise ~/codex-overlay
cd ~/codex-overlay && git init && git add -A && git commit -m "chore: work overlay"
```

Keep it local, or push it to the company's own git host. Never push it to a personal account.

## 3. Fill the slots

| File | What goes in it |
|---|---|
| `overlay.toml` | `core_version` matching the tag you downloaded. Keep `core_writable = false`. |
| `profiles.toml` | One model ID per tier (`default`, `deep`, `bulk`, `review`), from the models the company allows. `doctor` checks each against Codex's model catalog. |
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

On Windows: `set CODEX_HARNESS_OVERLAY=%USERPROFILE%\codex-overlay`, `set PYTHONPATH=.`, then `py -m harness install` and `py -m harness doctor`.

Fix every FAIL. `--live` runs the zero-token prompt and rules probes and one short request per tier, so it spends a few tokens; skip it if usage is strictly metered.

## 5. First run

- If plugins are allowed, install superpowers: `codex plugin add superpowers@openai-curated-remote`.
- The first interactive session asks once to trust the `Stop` hook. Accept, or the tracker never collects.

## Day to day

- `python -m harness tokens` shows where tokens go. Numbers for the deck go in `docs/deck/data.local.js` on this machine only; it is gitignored.
- Improvements go into overlay slots through the `improve` skill, then `install` and `doctor`.
- To upgrade: get the new tag, bump `core_version`, run `install` and `doctor`.

## What never leaves the work machine

The overlay, numbers measured at work, internal names, hosts, people and code. The `improve` skill ends with upstream candidates written in generic terms; restate them by hand on the bench machine if they help anyone.
