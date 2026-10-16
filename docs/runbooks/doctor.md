# Runbook: reading doctor

`doctor` checks that Codex, the core, the overlay and the files `install` wrote all agree. Run it after every `install`, after every Codex update, and whenever Codex behaves differently than you expect.

```sh
PYTHONPATH=<core> python3 -m codejig --overlay <overlay> doctor          # free
PYTHONPATH=<core> python3 -m codejig --overlay <overlay> doctor --live   # spends a few tokens
PYTHONPATH=<core> python3 -m codejig doctor --check-binary               # only the binary scan
```

Each line is `<level> <check>: <detail>`. `ok` is fine, `warn` needs a look, `FAIL` makes doctor exit 1. Run it from inside a repo you work in: the AGENTS.md chain and the prompt probe read the current directory.

## Checks

| Check | What it looks at | When it is not ok | Fix |
|---|---|---|---|
| `codex keys` | The Codex binary contains the 11 config keys the pack writes. | A key is missing: this Codex version renamed or dropped a setting the pack relies on. A "launcher" FAIL means it found a wrapper script. | Pass `--codex-bin` with the native binary, or set `CODEX_BIN`. A missing key after an update: see [upgrade-and-rollback](upgrade-and-rollback.md). |
| `core pin` | The core checkout is exactly at the tag in `overlay.toml` `core_version`. | FAIL on a work machine, warn on the bench. | Check out the pinned tag, or bump `core_version`. |
| `core clean` | No local edits in the core. | FAIL when `core_writable = false` and the core has edits. | Move the change into an overlay slot, then `git checkout .` in the core. |
| `global AGENTS.md` | `$CODEX_HOME/AGENTS.md` matches what `install` would write; no `AGENTS.override.md`. | Missing or stale: run `install`. A non-empty `AGENTS.override.md` hides the generated file. | Delete or empty `AGENTS.override.md`, then `install`. |
| `legacy profiles` | `config.toml` has no `profile =` or `[profiles.*]` for a tier name. | Codex refuses `--profile` when both exist. | Delete those entries from `config.toml`. |
| `tier <t> profile` | `<t>.config.toml` exists and is unedited. | Missing: Codex silently runs the base config. Edited: your edit is lost on the next `install`. | Put the change in `profiles.toml` or `guardian-policy.md`, then `install`. |
| `model catalog` | `models_cache.json` is readable. | Codex has not been started yet on this machine. | Start `codex` once, quit, rerun doctor. |
| `tier <t> model` | The tier's model is in this account's catalog and supports the tier's effort. | The detail lists the models this account can use. | Pick one of them in `profiles.toml`, then `install`. |
| `review family` | `review` and `default` use different model families. | Same family reviews with the same blind spots. | Use a different family for `review` if the account has one. A warn is acceptable if not. |
| `explorer role`, `reviewer role`, `judge role` | `$CODEX_HOME/agents/<role>.toml` exists and is current, and its tier differs from `default`. | Missing or stale: subagents of that kind run on the parent's model. Same as `default`: the role saves nothing. | `install`; give `bulk` a cheaper model than `default` in `profiles.toml`. |
| `git gate` | With `git_gate = true`: the global `core.hooksPath` points at the gate, and the current repo does not override it. | Not active: another tool owns `core.hooksPath`. Overridden: the repo sets its own (husky and similar). Off in the overlay but still active: run `install`. | As the detail says; see [commit-attribution](commit-attribution.md). |
| `stop hook` | `hooks.json` has the collector's `Stop` hook. | Not registered: the tracker never collects. | `install`, then accept the trust prompt in the next interactive session. |
| `knowledge` | `knowledge/INDEX.md` exists and is 150 lines or fewer. | Too long, or no index. | Merge or delete facts; see the `improve` skill. |
| `superpowers` | The superpowers plugin is installed. | Not installed. | `codex plugin add superpowers@openai-curated-remote`, if plugins are allowed. |
| `managed requirements` | Reads the machine's managed `requirements.toml`, if any. | FAIL only if it cannot be parsed. Requirements pushed from the cloud are invisible to doctor. | Ask IT what is enforced. |
| `guardian allowed` | Managed config allows `auto_review`. | FAIL: every tier profile sets it, so every tier is refused. | Ask IT, or drop `approvals_reviewer` from the tiers (a core change). |
| `overlay rules` | Managed `ignore_rules` does not list a tier's model. | Your `allow` rules do nothing for that model. | Expected on locked-down machines; rely on Guardian. |
| `hooks` | Managed `allow_managed_hooks_only` is off. | The tracker's hook will not run. | Ask IT, or live without the tracker. |
| `guardian policy` | No managed `guardian_extra_policy`. | Managed text replaces your `guardian-policy.md`. | Ask IT to include your additions, or accept theirs. |
| `bench diff` | Managed requirements against `bench/requirements.toml`, the bench's simulation of a locked machine. | Differences mean the bench tested a different lock-down than this machine has. Always a warn on a machine with no managed file. | Informational. On a work machine, note the differences when you report a bug. |
| `prompt probe <t>` | `codex --profile <t> debug prompt-input` loads, the generated AGENTS.md reaches the prompt, every skill is listed. Zero tokens. | AGENTS.md missing from the prompt: an override file or the size cap. Skills missing: run `install`. | As the detail says. |
| `skills catalog` | Size of the skills list Codex sends with every request, from the same probe. | Over 8,000 bytes: the detail names the five largest entries. | In `config.toml`, add `[[skills.config]]` with `name = "<skill>"` and `enabled = false` for each skill this machine never uses. |
| `rules load` | `codex execpolicy check` loads every `*.rules` file. | One bad file makes Codex drop every rule, `default.rules` included. | Fix or remove the file the error names. |
| `live probe <t>` | With `--live`: one short request per tier reports the model and effort it started. | Codex started something else than the tier says. | Check `config.toml` for overrides and managed config for a forced model. |
| `AGENTS.md chain` | Total size of the global and project AGENTS.md files for the current directory. | Over 80% of `project_doc_max_bytes` (32 KiB by default) warns; over it fails, because Codex silently stops adding files past the cap. | Shorten the repo's AGENTS.md, or move detail into `knowledge/`. |
