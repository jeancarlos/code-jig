# Runbook: reading the token report

The `Stop` hook copies every finished Codex turn from the rollout files into `~/.local/share/code-jig/usage.sqlite3`. Nothing leaves the machine. `tokens` summarises it.

```sh
PYTHONPATH=<core> python3 -m codejig tokens                 # last 7 days
PYTHONPATH=<core> python3 -m codejig tokens --days 30 --top 20
PYTHONPATH=<core> python3 -m codejig collect --rescan       # rebuild after a hook gap
```

Whether code-jig is worth its tokens is a different question; see [evidence.md](evidence.md).

If `tokens` says the database is missing, the hook has never run: check `doctor`'s `stop hook` line and accept the trust prompt in an interactive session. Then run `collect` once by hand.

## The report, line by line

| Line | Meaning | Look at it when |
|---|---|---|
| `Input ... cached ... output ...` | All input tokens, the share served from the prompt cache, all output tokens. Input dominates: every model request re-sends the whole context. | Cache below about 90% overall means context keeps changing under the model. |
| `Guardian share of input` | Share of input spent on Guardian reviews, how many reviews, input per review. | A high share means many commands are escalated. See the escalations list. |
| `Sessions over 300 model requests` | Long threads. Each request re-reads everything before it. | Start a new thread per task; the core AGENTS.md asks Codex for the same. |
| `Top sessions` | Per thread: own input, cache hit, model requests, compactions, polling calls (`sleep`/`wait`), Guardian input, subagent input. `LOW` marks a cache hit under `--cache-floor` (97.5% by default). | A `LOW` session usually switched model or effort mid-thread, or had a large file rewritten repeatedly. Many polling calls means the agent waited in a loop. |
| `Escalations sent to Guardian, by command` | Commands that asked to leave the sandbox, grouped by their first word or two. | A routine command near the top is a candidate for a `guardian-policy.md` line, or as a last resort an overlay rule. Read [circuit-breaker](circuit-breaker.md) and ADR 0009 first. |
| `By model` | Input and output per model. | Check that tiers do what you expect: bulk work on the `bulk` model, not the `deep` one. |
| `warning: N rollout lines quarantined` | Lines the collector could not parse; they are kept in the `quarantine` table, not counted. | After a Codex update, a jump here means the rollout format changed. Report it with the Codex version. |

## What to change

- High Guardian share, same command again and again: describe when it is acceptable in `guardian-policy.md`, then `install`.
- Long sessions and low cache: one task per thread; do not switch `--profile` or reasoning effort inside a thread.
- Large own input on a single session: the repo's AGENTS.md or a tool output may be huge. `doctor` shows the AGENTS.md chain size. Codex caps tool output with `tool_output_token_limit`.

## Grafana

`dashboard.json` is a Grafana dashboard for the frser-sqlite datasource pointed at the same database. Use it only on a Grafana instance you are already allowed to run; the CLI report needs nothing extra.
